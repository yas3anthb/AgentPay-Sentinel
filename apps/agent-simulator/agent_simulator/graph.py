"""LangGraph state machine for the agent's decision flow.

    search ─► build_cart ─► propose_payment ─► handle_gateway_response
                                                    │
                        ┌───────────────────────────┼──────────────────┐
                        ▼                           ▼                  ▼
                    completed                  await_approval        blocked
                     (ALLOW)                 (REQUIRE_APPROVAL)      (BLOCK)
                                                    │
                                          external signal only
                                                    ▼
                                        submit_approved_payment ─► completed

Two properties are enforced by the graph's *shape*, not by prompting:

  1. `blocked` is terminal. There is no edge from it back to `build_cart` or
     `propose_payment`, so a blocked agent cannot retry with a smaller amount,
     a different merchant, or edited content to route around the decision.
     `test_blocked_is_terminal_with_no_path_back_to_payment` asserts this by
     walking the compiled graph, so a future edit that adds such an edge fails
     the test rather than quietly weakening the demo.

  2. `await_approval` does not loop or poll. The graph interrupts before
     `submit_approved_payment` and stops. It resumes only when an external
     caller supplies an approval token via the service's /approve endpoint.
"""
from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any, Literal, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .config import Settings, SimulatorError
from .sentinel import PaymentIntentArgs, SentinelClient, build_sentinel_tool
from .storefront import CATALOG, PAGES, Product, build_storefront_tools, search_catalog
from .transcript import StepKind, Transcript

log = logging.getLogger("agent_simulator.graph")

Outcome = Literal["", "ALLOW", "REQUIRE_APPROVAL", "BLOCK", "ERROR"]


class ShopperState(TypedDict, total=False):
    instruction: str
    budget: str
    adversarial: bool
    requested_quantity: int

    # research output
    chosen_sku: str
    page_url: str
    page_content: str
    merchant_id: str
    merchant_verified: bool
    source_type: str

    # cart output
    cart: list[dict[str, Any]]
    total: str
    currency: str
    review_verdict: str

    # gateway output
    decision: Outcome
    reason_codes: list[str]
    gateway_response: dict[str, Any]
    approval_request_id: str
    approval_token: str

    status: str
    error: str


class GraphDeps:
    """Everything the nodes need, kept off the state so the state stays JSON."""

    def __init__(
        self,
        settings: Settings,
        transcript: Transcript,
        client: SentinelClient,
        *,
        adversarial: bool,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self.settings = settings
        self.transcript = transcript
        self.client = client
        self.adversarial = adversarial
        # One id for the whole run: every gateway call this run makes carries it
        # as X-Request-Id, so the live pipeline stream and the audit trail are
        # both filterable to this exact run.
        self.correlation_id = correlation_id
        self.storefront_tools = build_storefront_tools(transcript, adversarial=adversarial)
        self.payment_tool = build_sentinel_tool(
            client,
            transcript,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )
        self.agents: tuple[Any, Any] | None = None
        self.llm: Any = None

    def ensure_crew(self) -> tuple[Any, Any]:
        """Build the crew lazily, so offline runs never touch the LLM layer."""
        if self.agents is None:
            from .crew import build_agents
            from .llm import build_crew_llm

            self.llm = build_crew_llm(self.settings)
            self.agents = build_agents(
                self.settings,
                self.llm,
                self.storefront_tools,
                self.payment_tool,
                self.transcript,
            )
        return self.agents


def _note(deps: GraphDeps, node: str, summary: str, detail: dict | None = None) -> None:
    deps.transcript.add(
        StepKind.GRAPH_TRANSITION, actor="langgraph", name=node, summary=summary,
        detail=detail or {},
    )


# --- nodes -----------------------------------------------------------------


def make_nodes(deps: GraphDeps) -> dict[str, Any]:
    offline = deps.settings.offline()

    def search(state: ShopperState) -> ShopperState:
        _note(deps, "search", "researching candidates")
        instruction = state["instruction"]

        if not offline:
            from .crew import research_task, run_crew
            from .llm import wrap_llm_errors

            try:
                # Crew construction is inside the try too: building the LLM can
                # fail (bad key, unreachable provider) just as readily as
                # calling it, and both must surface as an explicit error rather
                # than escaping as a bare RuntimeError.
                shopper, _ = deps.ensure_crew()
                run_crew([research_task(shopper, instruction)], [shopper], deps.settings,
                         deps.transcript)
            except SimulatorError:
                raise
            except Exception as exc:
                raise wrap_llm_errors(exc) from exc

        # Whether or not an LLM narrated it, the concrete selection is read
        # back from the tools deterministically: the state machine must hold a
        # real SKU and the real page bytes, not a model's paraphrase of them.
        search_tool, fetch_tool = deps.storefront_tools
        if offline:
            # No crew ran, so drive the tools directly. This matters for more
            # than tidiness: fetch_merchant_page is what records the payload's
            # SHA-256 at the tool boundary, and that record is the evidence the
            # adversarial demo uses to prove the injection reached the agent
            # unmodified. Skipping it would leave the claim unsupported.
            search_tool.func(query=instruction)

        results = search_catalog(instruction, adversarial=deps.adversarial)
        product: Product = results[0]

        already_fetched = any(
            step.name == "fetch_merchant_page"
            and step.detail.get("url") == product.page_url
            for step in deps.transcript.steps
        )
        if not already_fetched:
            # In live mode the crew normally fetches the page itself. If the
            # model chose not to, fetch it here anyway: the payload has to be
            # on the record either way, or the run proves nothing.
            fetch_tool.func(url=product.page_url)

        page = PAGES.get(product.page_url, "")

        _note(
            deps,
            "search",
            f"selected {product.sku} from {product.merchant_id}",
            {"sku": product.sku, "page_url": product.page_url, "page_chars": len(page)},
        )
        return {
            **state,
            "chosen_sku": product.sku,
            "page_url": product.page_url,
            "page_content": page,
            "merchant_id": product.merchant_id,
            "merchant_verified": product.merchant_verified,
            "source_type": product.source_type,
        }

    def build_cart(state: ShopperState) -> ShopperState:
        _note(deps, "build_cart", "building and reviewing the cart")
        product = CATALOG[state["chosen_sku"]]
        quantity = int(state.get("requested_quantity") or 1)
        total = f"{float(product.unit_price) * quantity:.2f}"

        verdict = "APPROVE (deterministic offline reviewer: cart matches the request)"
        if not offline:
            from .crew import cart_task, review_task, run_crew
            from .llm import wrap_llm_errors

            try:
                shopper, reviewer = deps.ensure_crew()
                verdict = run_crew(
                    [
                        cart_task(shopper, state["instruction"]),
                        review_task(reviewer, state["instruction"]),
                    ],
                    [shopper, reviewer],
                    deps.settings,
                    deps.transcript,
                )
            except SimulatorError:
                raise
            except Exception as exc:
                raise wrap_llm_errors(exc) from exc

        deps.transcript.add(
            StepKind.REVIEW,
            actor="reviewer",
            name="cart_review",
            summary=verdict[:280].replace("\n", " ").strip(),
            detail={"verdict": verdict},
        )
        return {
            **state,
            "cart": [
                {
                    "sku": product.sku,
                    "name": product.name,
                    "quantity": quantity,
                    "unit_price": product.unit_price,
                }
            ],
            "total": total,
            "currency": "INR",
            "review_verdict": verdict,
        }

    def propose_payment(state: ShopperState) -> ShopperState:
        _note(deps, "propose_payment", "calling the only money-moving tool")
        args = PaymentIntentArgs(
            merchant_id=state["merchant_id"],
            amount=state["total"],
            currency=state.get("currency", "INR"),
            items=state["cart"],
            purpose=state["instruction"][:2000],
            merchant_content=state.get("page_content", ""),
            merchant_source_type=state.get("source_type", "unknown"),
            merchant_source_url=state.get("page_url", ""),
            merchant_verified=state.get("merchant_verified", False),
        )
        # The same tool object the shopper agent holds. In live mode the crew
        # narrates its way here; either way this is the single call that can
        # move money, and it is the gateway that answers.
        try:
            deps.payment_tool.func(**args.model_dump())
        except SimulatorError:
            raise

        decision_step = next(
            (s for s in reversed(deps.transcript.steps) if s.kind is StepKind.GATEWAY_DECISION),
            None,
        )
        response = decision_step.detail if decision_step else {}
        return {
            **state,
            "decision": response.get("decision", "ERROR"),
            "reason_codes": response.get("reason_codes", []),
            "gateway_response": response,
        }

    def handle_gateway_response(state: ShopperState) -> ShopperState:
        decision = state.get("decision", "ERROR")
        _note(
            deps,
            "handle_gateway_response",
            f"gateway said {decision}",
            {"reason_codes": state.get("reason_codes", [])},
        )
        return state

    def blocked(state: ShopperState) -> ShopperState:
        codes = state.get("reason_codes", [])
        _note(deps, "blocked", "terminating; a BLOCK is final", {"reason_codes": codes})
        deps.transcript.add(
            StepKind.NOTE,
            actor="langgraph",
            name="no_retry",
            summary=(
                "Run terminated. The graph has no edge from blocked back to "
                "payment, so there is no path that could resubmit a modified "
                "request to get a different answer."
            ),
            detail={"reason_codes": codes},
        )
        return {**state, "status": "blocked"}

    def await_approval(state: ShopperState) -> ShopperState:
        response = state.get("gateway_response", {})
        pa_id = response.get("payment_authorization_id", "")
        approval_request_id = f"ar_{pa_id[3:]}" if pa_id.startswith("pa_") else ""
        _note(
            deps,
            "await_approval",
            "paused for a human; not polling, not looping",
            {"approval_request_id": approval_request_id},
        )
        return {
            **state,
            "status": "awaiting_approval",
            "approval_request_id": approval_request_id,
        }

    def submit_approved_payment(state: ShopperState) -> ShopperState:
        """Runs only after an external caller resumes the graph with a token."""
        _note(deps, "submit_approved_payment", "resubmitting with the human's approval token")
        product = CATALOG[state["chosen_sku"]]
        args = PaymentIntentArgs(
            merchant_id=state["merchant_id"],
            amount=state["total"],
            currency=state.get("currency", "INR"),
            items=state["cart"],
            purpose=state["instruction"][:2000],
            merchant_content=state.get("page_content", ""),
            merchant_source_type=state.get("source_type", "unknown"),
            merchant_source_url=state.get("page_url", ""),
            merchant_verified=state.get("merchant_verified", False),
            approval_token=state.get("approval_token") or None,
        )
        approved_tool = build_sentinel_tool(
            deps.client,
            deps.transcript,
            idempotency_key=f"crew-approved-{uuid.uuid4().hex[:12]}",
            correlation_id=deps.correlation_id,
        )
        approved_tool.func(**args.model_dump())
        decision_step = next(
            (s for s in reversed(deps.transcript.steps) if s.kind is StepKind.GATEWAY_DECISION),
            None,
        )
        response = decision_step.detail if decision_step else {}
        status = "completed" if response.get("decision") == "ALLOW" else "blocked"
        return {
            **state,
            "decision": response.get("decision", "ERROR"),
            "reason_codes": response.get("reason_codes", []),
            "gateway_response": response,
            "status": status,
        }

    def completed(state: ShopperState) -> ShopperState:
        _note(deps, "completed", "payment authorized and settled")
        return {**state, "status": "completed"}

    return {
        "search": search,
        "build_cart": build_cart,
        "propose_payment": propose_payment,
        "handle_gateway_response": handle_gateway_response,
        "blocked": blocked,
        "await_approval": await_approval,
        "submit_approved_payment": submit_approved_payment,
        "completed": completed,
    }


def route_on_decision(state: ShopperState) -> str:
    decision = state.get("decision", "ERROR")
    if decision == "ALLOW":
        return "completed"
    if decision == "REQUIRE_APPROVAL":
        return "await_approval"
    return "blocked"


def build_graph(deps: GraphDeps):
    nodes = make_nodes(deps)
    graph = StateGraph(ShopperState)
    for name, fn in nodes.items():
        graph.add_node(name, fn)

    graph.add_edge(START, "search")
    graph.add_edge("search", "build_cart")
    graph.add_edge("build_cart", "propose_payment")
    graph.add_edge("propose_payment", "handle_gateway_response")
    graph.add_conditional_edges(
        "handle_gateway_response",
        route_on_decision,
        {"completed": "completed", "await_approval": "await_approval", "blocked": "blocked"},
    )

    # A blocked run ends. Deliberately no edge back to build_cart or
    # propose_payment: the agent cannot negotiate with the policy engine.
    graph.add_edge("blocked", END)
    graph.add_edge("completed", END)

    # await_approval -> submit_approved_payment exists, but the compiled graph
    # interrupts before it, so it never runs on its own. Only an external
    # resume can advance past this point.
    graph.add_edge("await_approval", "submit_approved_payment")
    graph.add_edge("submit_approved_payment", END)

    return graph.compile(
        checkpointer=MemorySaver(),
        interrupt_before=["submit_approved_payment"],
    )
