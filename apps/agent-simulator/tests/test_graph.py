"""The state machine's shape is a security property, so it gets tested."""
from __future__ import annotations

import pytest

from agent_simulator.config import get_settings
from agent_simulator.graph import GraphDeps, build_graph, route_on_decision
from agent_simulator.sentinel import SentinelClient
from agent_simulator.transcript import Transcript


@pytest.fixture
def compiled():
    settings = get_settings()
    deps = GraphDeps(settings, Transcript(), SentinelClient(settings), adversarial=False)
    return build_graph(deps)


def edges(compiled) -> set[tuple[str, str]]:
    return {(e.source, e.target) for e in compiled.get_graph().edges}


def test_graph_models_the_declared_flow(compiled):
    e = edges(compiled)
    assert ("__start__", "search") in e
    assert ("search", "build_cart") in e
    assert ("build_cart", "propose_payment") in e
    assert ("propose_payment", "handle_gateway_response") in e


def test_blocked_is_terminal_with_no_path_back_to_payment(compiled):
    """A BLOCK ends the run. The agent cannot resubmit a modified payload to
    route around the policy engine, because no edge exists that would let it."""
    outgoing = {t for s, t in edges(compiled) if s == "blocked"}
    assert outgoing == {"__end__"}

    into_payment = {s for s, t in edges(compiled) if t == "propose_payment"}
    assert into_payment == {"build_cart"}
    into_build = {s for s, t in edges(compiled) if t == "build_cart"}
    assert into_build == {"search"}


def test_approval_pauses_rather_than_looping(compiled):
    e = edges(compiled)
    assert ("handle_gateway_response", "await_approval") in e
    assert ("await_approval", "submit_approved_payment") in e
    assert ("await_approval", "await_approval") not in e
    assert ("await_approval", "propose_payment") not in e


def test_resume_node_is_gated_by_an_interrupt(compiled):
    """`submit_approved_payment` must never run on its own — only an external
    resume can advance past the interrupt."""
    assert "submit_approved_payment" in compiled.interrupt_before_nodes


@pytest.mark.parametrize(
    "decision,expected",
    [
        ("ALLOW", "completed"),
        ("REQUIRE_APPROVAL", "await_approval"),
        ("BLOCK", "blocked"),
        ("ERROR", "blocked"),
        ("", "blocked"),
        ("something-unexpected", "blocked"),
    ],
)
def test_routing_defaults_to_blocked(decision, expected):
    """Deny by default, in the agent as well as the gateway: anything that is
    not an explicit ALLOW or approval request ends the run."""
    assert route_on_decision({"decision": decision}) == expected


def test_routing_with_no_decision_at_all_blocks():
    assert route_on_decision({}) == "blocked"
