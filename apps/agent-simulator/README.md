# Agent Simulator

A real agentic-commerce stack — **CrewAI** agents, **LangChain** tools, a
**LangGraph** state machine — whose only way to move money is the AgentPay
Sentinel gateway.

The point of this service is to make the demo honest. A hand-rolled script that
POSTs a payload proves nothing about agent security; a real crew, reading real
scraped content through real tool calls, getting hijacked by a real injection,
and being stopped by the gateway anyway — that proves something.

```
        LangGraph (orchestration + the no-retry guarantee)
   search ─► build_cart ─► propose_payment ─► handle_gateway_response
      │           │              │                      │
   CrewAI      CrewAI         CrewAI          ┌─────────┼──────────┐
  shopper   shopper +        shopper          ▼         ▼          ▼
            reviewer      (Sentinel tool)  completed  await_    blocked
                                            (ALLOW)  approval   (BLOCK)
                                                        │      terminal
                                              external signal only
```

## Run it

```bash
docker compose up -d --build           # from the repo root; starts everything
curl -X POST localhost:9200/simulate/clean-purchase -d '{}' -H 'content-type: application/json'
curl -X POST localhost:9200/simulate/adversarial    -d '{}' -H 'content-type: application/json'
```

| Endpoint | |
|---|---|
| `POST /simulate/clean-purchase` | the honest path; ends in ALLOW |
| `POST /simulate/adversarial` | poisoned merchant page; ends in BLOCK |
| `POST /simulate/approval-flow` | over the approval threshold; **pauses** |
| `POST /simulate/{run_id}/approve` | the external signal that resumes a paused run |
| `POST /simulate/reset` | dev-only; clears gateway demo state |
| `GET /simulate/runs` · `GET /simulate/runs/{id}` | past runs |
| `GET /healthz` · `GET /readyz` | ops |

Every response carries the full structured transcript — tool calls, tool
results, CrewAI step summaries, graph transitions, and the Sentinel decision —
so a frontend can animate a real run step by step.

## The four properties worth checking

### 1. There is exactly one money-moving tool

The shopper's entire toolset is `product_search`, `fetch_merchant_page`, and
`propose_payment_intent`. There is no `charge_card`, no provider client, no
stored credential anywhere in this package. The agent holds a delegation token
and a URL; everything else is Sentinel's call.

`test_only_one_money_moving_tool_exists` fails if anyone adds a second payment
path, and `test_shopper_toolset_contains_exactly_the_declared_tools` checks
what the CrewAI `Agent` actually ends up holding rather than what we intended
to give it.

The tool's description tells the agent the same thing in its own terms —
including that a BLOCK is final and must not be retried around.

### 2. The injection reaches the agent unmodified

If CrewAI or LangChain sanitised the payload upstream, the demo would prove
nothing about the gateway. So `fetch_merchant_page` returns the poisoned page
byte-for-byte and records its SHA-256 at the tool boundary;
`/simulate/adversarial` reports `injection.reached_agent_unmodified`, and
`test_injection_reached_the_agent_unmodified` pins the exact hash.

Neither framework filtered it. The block happens at Sentinel, which is the
whole claim.

### 3. A BLOCK is structurally final

`blocked` is a terminal node with exactly one outgoing edge, to `END`. There is
no path from it back to `build_cart` or `propose_payment`, so the agent cannot
resubmit a smaller amount or edited content to negotiate with the policy
engine. This is enforced by the graph's shape, not by prompting — a prompt can
be argued with.

`test_blocked_is_terminal_with_no_path_back_to_payment` walks the compiled
graph, so a future edit that adds such an edge fails the test.

Routing also denies by default: anything that is not an explicit `ALLOW` or
`REQUIRE_APPROVAL` routes to `blocked`.

### 4. Approval pauses; it does not poll

On `REQUIRE_APPROVAL` the graph interrupts before `submit_approved_payment` and
stops. Nothing loops, nothing polls. The run advances only when
`POST /simulate/{run_id}/approve` grants the approval at the gateway and
resumes the checkpointed graph with the returned token — which Sentinel then
re-checks against the live transaction.

## LLM modes

The crew's LLM is configured **separately** from the gateway's injection
classifier. They may share a key value, but they are distinct clients in
distinct processes, so a key problem on one side surfaces there instead of
being silently absorbed by the other.

| `AGENT_LLM_MODE` | behaviour |
|---|---|
| `live` (default) | real CrewAI agents. No key ⇒ hard error, never a fake run. |
| `offline` | deterministic scripted reasoning, loudly labelled. |

Offline mode exists so the demo and the frontend have something to render
without a key. It is not a quiet fallback:

- the response carries `mode: "offline-deterministic"`, `simulated_reasoning:
  true`, and a `warning` explaining exactly what was scripted;
- every scripted transcript step is individually flagged `simulated: true`;
- **every Sentinel round-trip is flagged `simulated: false`**, because it is
  real. In offline mode the agent's reasoning is a script; the decision, reason
  codes, risk signals and audit hashes still came from the live gateway.

A failed live run returns HTTP 502 with an error code and no transcript at all:

```json
{"error": "AGENT_LLM_FAILED", "message": "The agent's LLM call failed (AuthenticationError): ..."}
```

## Environment

| Variable | Default | |
|---|---|---|
| `GATEWAY_URL` | `http://localhost:8080` | the Sentinel gateway |
| `PROVIDER_URL` | `http://localhost:9100` | mock provider, read-only (call counter) |
| `AGENT_LLM_MODE` | `live` | `live` or `offline` |
| `AGENT_OPENAI_API_KEY` | falls back to `OPENAI_API_KEY` | the crew's key |
| `AGENT_MODEL` | `gpt-4o-mini` | |
| `AGENT_MAX_ITERATIONS` | `6` | crew iteration cap |
| `CREW_VERBOSE` | `false` | CrewAI's own console output |

## Tests

```bash
make agent-test        # from the repo root
```

33 tests. The structural ones (tools, graph shape) need nothing; the end-to-end
ones need `docker compose up` and are skipped otherwise. They reset the
gateway's demo state once per session — the rolling daily budget and the
5-minute duplicate fingerprint are real controls that accumulate across runs,
and resetting is honest where disabling them would not be.

## Why a separate venv and image

CrewAI's dependency tree pins **pydantic 2.12** and **openai 2.x**; the gateway
pins pydantic 2.10.4 and openai 1.59.6. Installing both in one environment
would silently upgrade the gateway's dependencies out from under its test
suite. The two services never share an environment or an image.

## Known rough edges

- **`crewai.tools.BaseTool.from_langchain` is broken in 1.15.18** — it calls
  `cls(...)` on the abstract base, whose `_run` is unimplemented, so it raises
  `TypeError` for every input. `LangChainToolAdapter` in `crew.py` does the
  conversion by hand and holds the original LangChain tool, so the crew and the
  graph invoke the same callable rather than two copies.
- **Endpoints are synchronous.** CrewAI raises if `kickoff()` is called from
  inside a running event loop, so these run in FastAPI's threadpool.
- **The reviewer agent is not a security control.** It is another LLM, and the
  same content that targets the shopper can talk it round. It is there to show
  a sensible agent-side check — and then to show Sentinel catching what gets
  past it.
- **Repeated identical runs vary the cart quantity.** Sentinel's fingerprint
  covers a 5-minute window, so buying the identical cart twice inside it is a
  duplicate and gets blocked. Each demo run buys a genuinely different quantity
  rather than defeating the check.
