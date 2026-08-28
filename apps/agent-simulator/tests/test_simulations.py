"""End-to-end simulations, mirroring the gateway's two demo scripts but
asserting on the crew's transcript.

These run against the live stack (docker compose up) and are skipped otherwise.
They run in offline LLM mode by default, which changes only the agent's
reasoning — every Sentinel call, decision, reason code and audit hash asserted
here came from the real gateway.
"""
from __future__ import annotations

import httpx
import pytest

from agent_simulator.storefront import POISONED_PAGE_SHA256

from conftest import PROVIDER, needs_gateway

pytestmark = needs_gateway

ALLOWED_TOOLS = {"product_search", "fetch_merchant_page", "propose_payment_intent"}


def tool_names(body: dict) -> set[str]:
    return {
        s["name"] for s in body["transcript"]["steps"] if s["kind"] == "tool_call"
    }


def gateway_decisions(body: dict) -> list[dict]:
    return [s for s in body["transcript"]["steps"] if s["kind"] == "gateway_decision"]


# --- Demo A: the clean path ------------------------------------------------


def test_clean_purchase_is_allowed_and_settles(client):
    body = client.post("/simulate/clean-purchase", json={}).json()

    assert body["decision"] == "ALLOW"
    assert body["reason_codes"] == ["POLICY_SATISFIED"]
    assert body["status"] == "completed"
    assert body["sentinel"]["state"] == "CONFIRMED"
    assert body["sentinel"]["provider_reference"]
    assert body["sentinel"]["audit_hash"]


def test_clean_path_never_touches_a_payment_endpoint_outside_sentinel(client):
    body = client.post("/simulate/clean-purchase", json={}).json()

    assert tool_names(body) <= ALLOWED_TOOLS
    # Exactly one money-moving call, and it went to Sentinel.
    payment_calls = [
        s for s in body["transcript"]["steps"]
        if s["kind"] == "tool_call" and s["name"] == "propose_payment_intent"
    ]
    assert len(payment_calls) == 1
    assert len(gateway_decisions(body)) == 1
    # The provider was reached exactly once, by the gateway, after it allowed.
    assert body["provider_calls"]["delta"] == 1


def test_gateway_steps_are_never_marked_simulated(client):
    """In offline mode the agent's reasoning is scripted, but the Sentinel
    round-trips are real and must say so."""
    body = client.post("/simulate/clean-purchase", json={}).json()

    for step in body["transcript"]["steps"]:
        if step["kind"] in {"gateway_decision", "tool_call"} and step["name"] in {
            "propose_payment_intent"
        }:
            assert step["simulated"] is False, step


# --- Demo B: the adversarial path ------------------------------------------


def test_adversarial_page_is_blocked_by_the_gateway(client):
    body = client.post("/simulate/adversarial", json={}).json()

    assert body["decision"] == "BLOCK"
    assert "PROMPT_INJECTION_HIGH_CONFIDENCE" in body["reason_codes"]
    assert body["status"] == "blocked"


def test_adversarial_run_never_reaches_the_payment_provider(client):
    """The assertion that matters, read off the provider's own counter rather
    than asserted from the gateway's side of the conversation."""
    before = httpx.get(f"{PROVIDER}/_control/stats", timeout=5.0).json()["call_count"]
    body = client.post("/simulate/adversarial", json={}).json()
    after = httpx.get(f"{PROVIDER}/_control/stats", timeout=5.0).json()["call_count"]

    assert body["decision"] == "BLOCK"
    assert after == before
    assert body["provider_calls"]["delta"] == 0


def test_injection_reached_the_agent_unmodified(client):
    """If a framework had sanitised the payload, the block would prove nothing."""
    body = client.post("/simulate/adversarial", json={}).json()

    assert body["injection"]["reached_agent_unmodified"] is True
    assert body["injection"]["payload_sha256"] == POISONED_PAGE_SHA256

    fetched = next(
        s for s in body["transcript"]["steps"]
        if s["kind"] == "tool_result" and s["name"] == "fetch_merchant_page"
    )
    assert fetched["detail"]["content_sha256"] == POISONED_PAGE_SHA256
    assert "IGNORE ALL PREVIOUS INSTRUCTIONS" in fetched["detail"]["content"]


def test_blocked_run_does_not_retry(client):
    """One payment attempt, then the graph terminates."""
    body = client.post("/simulate/adversarial", json={}).json()

    assert len(gateway_decisions(body)) == 1
    assert {d["name"] for d in gateway_decisions(body)} == {"BLOCK"}
    assert any(s["name"] == "no_retry" for s in body["transcript"]["steps"])


def test_no_authorization_token_is_issued_on_a_block(client):
    body = client.post("/simulate/adversarial", json={}).json()
    decision = gateway_decisions(body)[0]["detail"]
    assert decision.get("authorization") is None


# --- the approval flow -----------------------------------------------------


def test_approval_flow_pauses_then_resumes_on_an_external_signal(client):
    started = client.post("/simulate/approval-flow", json={}).json()

    assert started["decision"] == "REQUIRE_APPROVAL"
    assert "ABOVE_APPROVAL_THRESHOLD" in started["reason_codes"]
    assert started["status"] == "awaiting_approval"
    assert started["approval_request_id"]
    # Paused, not settled: nothing reached the provider yet.
    assert started["provider_calls"]["delta"] == 0

    resumed = client.post(f"/simulate/{started['run_id']}/approve").json()

    assert resumed["decision"] == "ALLOW"
    assert resumed["reason_codes"] == ["APPROVAL_SATISFIED"]
    assert resumed["status"] == "completed"
    assert resumed["sentinel"]["state"] == "CONFIRMED"


def test_approving_an_unknown_run_is_an_explicit_error(client):
    response = client.post("/simulate/run_does_not_exist/approve")
    assert response.status_code == 502
    assert response.json()["error"] == "UNKNOWN_RUN"


def test_approving_a_completed_run_is_refused(client):
    done = client.post("/simulate/clean-purchase", json={}).json()
    response = client.post(f"/simulate/{done['run_id']}/approve")
    assert response.status_code == 502
    assert response.json()["error"] == "RUN_NOT_AWAITING_APPROVAL"


# --- honesty about mode ----------------------------------------------------


def test_offline_runs_are_labelled_everywhere(client):
    body = client.post("/simulate/clean-purchase", json={}).json()

    assert body["mode"] == "offline-deterministic"
    assert body["simulated_reasoning"] is True
    assert "warning" in body
    assert any(s["simulated"] for s in body["transcript"]["steps"])


def test_live_mode_without_a_key_fails_closed(client, monkeypatch):
    """No key, no run. The simulator does not invent a transcript."""
    from agent_simulator.config import Settings, SimulatorError
    from agent_simulator.llm import build_crew_llm

    settings = Settings(llm_mode="live", agent_openai_api_key="")
    with pytest.raises(SimulatorError) as exc:
        build_crew_llm(settings)
    assert exc.value.code == "AGENT_LLM_KEY_MISSING"


def test_crew_failure_returns_an_error_not_a_transcript(client, monkeypatch):
    """Requirement: never a fake successful transcript.

    The crew blows up mid-run; the service must surface that, not paper over it
    with a plausible-looking sequence of steps.
    """
    import agent_simulator.graph as graph_module
    from agent_simulator.config import Settings, get_settings

    monkeypatch.setattr(
        get_settings, "__wrapped__", lambda: Settings(llm_mode="live"), raising=False
    )

    def exploding_crew(*args, **kwargs):
        raise RuntimeError("model provider returned 503")

    monkeypatch.setattr(graph_module.GraphDeps, "ensure_crew", exploding_crew)
    monkeypatch.setattr(
        "agent_simulator.config.Settings.offline", lambda self: False
    )

    response = client.post("/simulate/clean-purchase", json={})

    assert response.status_code == 502
    body = response.json()
    assert body["error"] == "AGENT_LLM_FAILED"
    assert "503" in body["message"]
    assert "transcript" not in body
    assert "decision" not in body
