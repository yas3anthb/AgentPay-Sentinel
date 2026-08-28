"""The agent's capabilities, asserted rather than claimed."""
from __future__ import annotations

import hashlib

import pytest
from pydantic import BaseModel

from agent_simulator.crew import LangChainToolAdapter, adapt_tools, build_agents
from agent_simulator.config import Settings
from agent_simulator.sentinel import (
    PaymentIntentArgs,
    SENTINEL_TOOL_DESCRIPTION,
    SentinelClient,
    build_sentinel_tool,
)
from agent_simulator.storefront import (
    POISONED_PAGE,
    POISONED_PAGE_SHA256,
    build_storefront_tools,
    search_catalog,
)
from agent_simulator.transcript import StepKind, Transcript

MONEY_VERBS = ("pay", "charge", "checkout", "transfer", "purchase", "card", "wallet")


@pytest.fixture
def toolset():
    transcript = Transcript()
    storefront = build_storefront_tools(transcript, adversarial=True)
    payment = build_sentinel_tool(SentinelClient(), transcript)
    return transcript, storefront, payment


def test_only_one_money_moving_tool_exists(toolset):
    """The agent holds no payment credential and no second payment path.

    If someone later adds a `charge_card` or a raw HTTP tool to the shopper,
    this fails — which is the point. The demo's whole claim is that Sentinel is
    the only way out.
    """
    _, storefront, payment = toolset
    all_tools = [*storefront, payment]

    money_tools = [
        t for t in all_tools if any(verb in t.name.lower() for verb in MONEY_VERBS)
    ]
    assert [t.name for t in money_tools] == ["propose_payment_intent"]
    assert {t.name for t in storefront} == {"product_search", "fetch_merchant_page"}


def test_payment_tool_tells_the_agent_it_is_the_only_path(toolset):
    _, _, payment = toolset
    description = payment.description.lower()
    assert "only way to move money" in description
    assert "block" in description
    assert "do not resubmit" in description or "do not modify" in description


def test_payment_tool_args_schema_matches_the_gateway_contract(toolset):
    _, _, payment = toolset
    assert payment.args_schema is PaymentIntentArgs
    fields = set(PaymentIntentArgs.model_fields)
    assert {"merchant_id", "amount", "currency", "items"} <= fields
    # Money is a decimal string on the wire; the gateway rejects floats.
    assert PaymentIntentArgs.model_fields["amount"].annotation is str


def test_injection_payload_reaches_the_agent_byte_for_byte(toolset):
    """If CrewAI or LangChain sanitised the payload upstream, the demo would
    prove nothing about the gateway. This pins the raw bytes."""
    transcript, storefront, _ = toolset
    fetch = next(t for t in storefront if t.name == "fetch_merchant_page")

    returned = fetch.func(url="https://beans.example.net/p/colombian-1kg")

    assert returned == POISONED_PAGE
    assert hashlib.sha256(returned.encode()).hexdigest() == POISONED_PAGE_SHA256
    assert "IGNORE ALL PREVIOUS INSTRUCTIONS" in returned
    assert "alternate endpoint" in returned

    recorded = next(
        s for s in transcript.steps
        if s.kind is StepKind.TOOL_RESULT and s.name == "fetch_merchant_page"
    )
    assert recorded.detail["content_sha256"] == POISONED_PAGE_SHA256
    assert recorded.detail["is_known_injection_payload"] is True


def test_adversarial_search_surfaces_the_poisoned_listing_first():
    assert search_catalog("coffee", adversarial=True)[0].sku == "BEAN-COL-1KG"
    clean = search_catalog("coffee", adversarial=False)
    assert all(p.source_type != "scraped_page" for p in clean)


def test_adapter_preserves_the_langchain_tool_identity(toolset):
    """The crew and the graph must invoke the same callable, not two copies."""
    _, storefront, payment = toolset
    adapted = adapt_tools([*storefront, payment])

    assert all(isinstance(t, LangChainToolAdapter) for t in adapted)
    for original, wrapped in zip([*storefront, payment], adapted):
        assert wrapped.name == original.name
        assert wrapped.description == original.description
        assert wrapped.args_schema is original.args_schema
        assert wrapped.langchain_tool.func is original.func


def test_adapter_rejects_a_tool_without_a_schema():
    from langchain_core.tools import StructuredTool

    class NotAModel:
        pass

    tool = StructuredTool.from_function(
        func=lambda x: x, name="loose", description="no schema"
    )
    object.__setattr__(tool, "args_schema", None)
    with pytest.raises(TypeError):
        adapt_tools([tool])


def test_shopper_toolset_contains_exactly_the_declared_tools(toolset):
    """Belt and braces: check what the CrewAI Agent actually ends up holding."""
    transcript, storefront, payment = toolset
    from crewai import LLM

    settings = Settings()
    llm = LLM(model="gpt-4o-mini", api_key="sk-not-used-in-this-test")
    shopper, reviewer = build_agents(settings, llm, storefront, payment, transcript)

    assert sorted(t.name for t in shopper.tools) == [
        "fetch_merchant_page",
        "product_search",
        "propose_payment_intent",
    ]
    # The reviewer reads and opines. It cannot buy anything.
    assert reviewer.tools == []
