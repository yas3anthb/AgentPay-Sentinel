"""The bot's logic: it routes, formats, and relays. It never decides.

Telegram and the AgentPay services are faked; the handlers are exercised
directly.
"""
from __future__ import annotations

import pytest

from telegram_bot.config import Settings
from telegram_bot.handlers import format_decision, handle_callback, handle_message

SETTINGS = Settings(bot_username="AgentPayyashh_bot", default_budget="5000.00")


class FakeAPI:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.answered: list[str] = []

    async def send_message(self, chat_id, text, *, buttons=None, parse_mode="HTML"):
        self.sent.append({"chat_id": chat_id, "text": text, "buttons": buttons})
        return {"message_id": len(self.sent)}

    async def edit_message_text(self, *a, **k):
        return None

    async def answer_callback_query(self, cq_id, text=""):
        self.answered.append(cq_id)


class FakeBackend:
    def __init__(self, *, linked_as=None, run_summary=None, approve_summary=None):
        self.linked_as = linked_as
        self.run_summary = run_summary or {}
        self.approve_summary = approve_summary or {}
        self.calls: list[tuple] = []

    async def whoami(self, tid):
        return self.linked_as

    async def link_code(self, code, tid):
        self.calls.append(("link_code", code, str(tid)))
        if code.upper() == "LINK-GOOD01":
            return True, "user_ada"
        return False, "unknown link code"

    async def run(self, scenario, instruction, budget):
        self.calls.append(("run", scenario, instruction, budget))
        return self.run_summary

    async def approve_run(self, run_id):
        self.calls.append(("approve_run", run_id))
        return self.approve_summary


def _msg(text, tid=987654321, chat_id=987654321):
    return {"text": text, "from": {"id": tid}, "chat": {"id": chat_id}}


def _summary(decision, *, reason_codes=None, run_id="run_1", injection=None):
    return {
        "run_id": run_id,
        "decision": decision,
        "reason_codes": reason_codes or [],
        "status": "awaiting_approval" if decision == "REQUIRE_APPROVAL" else "completed",
        "sentinel": {"state": "CONFIRMED", "provider_reference": "ch_abc", "audit_hash": "a" * 64},
        "transcript": {
            "steps": [
                {
                    "kind": "tool_call",
                    "name": "propose_payment_intent",
                    "detail": {
                        "merchant_id": "merch_beanery",
                        "amount": "2400.00",
                        "currency": "INR",
                        "merchant_source_type": "official_api",
                        "items": [
                            {"name": "Ethiopian beans 1kg", "quantity": 2, "unit_price": "1200.00"}
                        ],
                    },
                }
            ]
        },
        **({"injection": injection} if injection else {}),
    }


async def test_start_shows_welcome():
    api, be = FakeAPI(), FakeBackend()
    await handle_message(api, be, SETTINGS, _msg("/start"))
    assert "link this chat" in api.sent[0]["text"].lower()


async def test_link_code_is_forwarded_and_confirmed():
    api, be = FakeAPI(), FakeBackend()
    await handle_message(api, be, SETTINGS, _msg("LINK-GOOD01"))
    assert ("link_code", "LINK-GOOD01", "987654321") in be.calls
    assert "linked to account" in api.sent[0]["text"].lower()


async def test_bad_link_code_reports_the_error():
    api, be = FakeAPI(), FakeBackend()
    await handle_message(api, be, SETTINGS, _msg("LINK-NOPE99"))
    assert "could not link" in api.sent[0]["text"].lower()


async def test_unlinked_user_is_told_to_link():
    api, be = FakeAPI(), FakeBackend(linked_as=None)
    await handle_message(api, be, SETTINGS, _msg("buy some coffee"))
    assert "not linked" in api.sent[0]["text"].lower()
    assert not any(c[0] == "run" for c in be.calls)  # never ran the agent


async def test_linked_user_instruction_runs_agent_and_shows_block():
    be = FakeBackend(
        linked_as="user_ada",
        run_summary=_summary(
            "BLOCK",
            reason_codes=["PROMPT_INJECTION_HIGH_CONFIDENCE"],
            injection={"reached_agent_unmodified": True, "payload_chars": 812},
        ),
    )
    api = FakeAPI()
    await handle_message(api, be, SETTINGS, _msg("restock the coffee"))
    assert ("run", "clean", "restock the coffee", "5000.00") in be.calls
    texts = " ".join(m["text"] for m in api.sent)
    assert "BLOCKED by policy" in texts
    assert "provider was never contacted" in texts
    # On a block there is no cart to confirm — it must NOT say "wants to buy";
    # the attempted cart is folded in as a past-tense "Attempted:" line.
    assert "wants to buy" not in texts
    assert "Attempted:" in texts and "refused before payment" in texts
    # a block never offers approval buttons
    assert all(m["buttons"] is None for m in api.sent)


async def test_attack_command_runs_the_adversarial_scenario():
    be = FakeBackend(linked_as="user_ada", run_summary=_summary("BLOCK", reason_codes=["X"]))
    api = FakeAPI()
    await handle_message(api, be, SETTINGS, _msg("/attack"))
    assert be.calls[0][0] == "run" and be.calls[0][1] == "adversarial"


async def test_require_approval_offers_approve_deny_buttons():
    be = FakeBackend(
        linked_as="user_ada",
        run_summary=_summary("REQUIRE_APPROVAL", reason_codes=["ABOVE_APPROVAL_THRESHOLD"], run_id="run_x"),
    )
    api = FakeAPI()
    await handle_message(api, be, SETTINGS, _msg("buy 8 bags of coffee"))
    last = api.sent[-1]
    assert "Approval needed" in last["text"]
    labels = [b["text"] for row in last["buttons"] for b in row]
    assert labels == ["✅ Approve", "❌ Deny"]
    assert last["buttons"][0][0]["callback_data"] == "approve:run_x"


async def test_approve_callback_resumes_the_run():
    be = FakeBackend(
        linked_as="user_ada",
        approve_summary=_summary("ALLOW", reason_codes=["APPROVAL_SATISFIED"]),
    )
    api = FakeAPI()
    cq = {
        "id": "cq1",
        "data": "approve:run_x",
        "message": {"chat": {"id": 111}},
    }
    await handle_callback(api, be, cq)
    assert ("approve_run", "run_x") in be.calls
    assert "cq1" in api.answered
    assert any("Allowed and paid" in m["text"] for m in api.sent)


async def test_deny_callback_charges_nothing():
    be = FakeBackend(linked_as="user_ada")
    api = FakeAPI()
    await handle_callback(api, be, {"id": "cq2", "data": "deny:run_x", "message": {"chat": {"id": 1}}})
    assert not any(c[0] == "approve_run" for c in be.calls)
    assert "Denied" in api.sent[0]["text"]


async def test_allowlist_blocks_a_stranger():
    s = Settings(allowlist=("111", "222"))
    api, be = FakeAPI(), FakeBackend(linked_as="user_ada")
    await handle_message(api, be, s, _msg("buy coffee", tid=999))
    assert "not open to this account" in api.sent[0]["text"].lower()
    assert be.calls == []


def test_format_decision_is_pure_and_covers_every_verdict():
    for d in ("ALLOW", "BLOCK", "REQUIRE_APPROVAL", "SOMETHING_ELSE"):
        text, buttons = format_decision(_summary(d, reason_codes=["R"]))
        assert isinstance(text, str) and text
        assert (buttons is not None) == (d == "REQUIRE_APPROVAL")
