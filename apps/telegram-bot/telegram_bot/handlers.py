"""Message and callback logic. Kept free of the polling loop so the tests can
drive it directly with fake updates.

The bot is a thin client:
  * identity  -> control plane (which account is this Telegram id)
  * agent run -> simulator
  * approval  -> gateway (via the simulator's resume)
It never decides an outcome. Every ALLOW / BLOCK / REQUIRE_APPROVAL comes back
from Sentinel and is only formatted here.
"""
from __future__ import annotations

import html
import logging
import re

from telegram_bot.api import TelegramAPI
from telegram_bot.backend import Backend
from telegram_bot.config import Settings

log = logging.getLogger("telegram_bot.handlers")

LINK_RE = re.compile(r"^LINK-[A-Z0-9]{4,}$", re.IGNORECASE)

WELCOME = (
    "<b>AgentPay Sentinel — demo bot</b>\n\n"
    "I run a real AI shopping agent, and every payment it proposes goes through "
    "the Sentinel policy firewall. I decide nothing myself.\n\n"
    "First, link this chat to an account:\n"
    "1. Open the web console → <b>Telegram</b> tab → <i>Generate link code</i>\n"
    "2. Send me that code (looks like <code>LINK-AB12CD</code>)\n\n"
    "Then just tell me what to buy, e.g.\n"
    "<i>Restock the office kitchen with coffee. Keep it under 5000 rupees.</i>\n\n"
    "/help for commands."
)

HELP = (
    "<b>Commands</b>\n"
    "<code>LINK-XXXXXX</code> — link this chat to your account\n"
    "/status — show which account this chat is linked to\n"
    "/attack — run the poisoned-merchant-page scenario (shows a block)\n"
    "any other text — treated as a purchase instruction for the agent\n"
)


def _esc(s: object) -> str:
    return html.escape(str(s))


_SYMBOL = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}


def _money(amount: object, currency: object) -> str:
    sym = _SYMBOL.get(str(currency).upper())
    return f"{sym}{_esc(amount)}" if sym else f"{_esc(amount)} {_esc(currency)}"


def _cart_from_summary(summary: dict) -> dict | None:
    steps = summary.get("transcript", {}).get("steps", [])
    for step in steps:
        if step.get("name") == "propose_payment_intent" and step.get("kind") == "tool_call":
            return step.get("detail")
    return None


def cart_oneline(summary: dict) -> str:
    """A compact 'what the agent assembled' line, for a BLOCK — where there is
    no cart to confirm or approve, only one that was refused."""
    cart = _cart_from_summary(summary)
    if not cart:
        return ""
    ccy = cart.get("currency", "INR")
    return (
        f"Attempted: {_money(cart.get('amount'), ccy)} at "
        f"{_esc(cart.get('merchant_id'))} — refused before payment."
    )


def format_cart(summary: dict) -> str:
    cart = _cart_from_summary(summary)
    if not cart:
        return "<i>The agent did not produce a cart.</i>"
    ccy = cart.get("currency", "INR")
    lines = ["<b>The agent wants to buy:</b>"]
    for it in cart.get("items", []):
        lines.append(
            f"• {_esc(it.get('name'))} ×{_esc(it.get('quantity'))} "
            f"— {_money(it.get('unit_price'), ccy)} each"
        )
    lines.append(
        f"Total: <b>{_money(cart.get('amount'), ccy)}</b> "
        f"at {_esc(cart.get('merchant_id'))}"
    )
    src = cart.get("merchant_source_type")
    if src:
        lines.append(f"Source: {_esc(src)}")
    return "\n".join(lines)


def format_decision(summary: dict) -> tuple[str, list[list[dict]] | None]:
    decision = summary.get("decision")
    reasons = ", ".join(summary.get("reason_codes") or []) or "—"
    sent = summary.get("sentinel", {})
    run_id = summary.get("run_id", "")

    if decision == "BLOCK":
        inj = summary.get("injection") or {}
        extra = ""
        if inj:
            extra = (
                f"\nAttack reached the agent unmodified: "
                f"{'yes' if inj.get('reached_agent_unmodified') else 'no'} "
                f"({inj.get('payload_chars', 0)} chars)"
            )
        return (
            f"🚫 <b>BLOCKED by policy</b>\n"
            f"Reasons: <code>{_esc(reasons)}</code>\n"
            f"No token was issued. The provider was never contacted."
            f"{extra}\n"
            f"Audit: <code>{_esc((sent.get('audit_hash') or '')[:16])}…</code>",
            None,
        )

    if decision == "REQUIRE_APPROVAL":
        return (
            f"🟡 <b>Approval needed</b>\n"
            f"Reasons: <code>{_esc(reasons)}</code>\n"
            f"Nothing is charged until you decide. The approval is bound to this "
            f"exact amount, merchant and cart.",
            [[
                {"text": "✅ Approve", "callback_data": f"approve:{run_id}"},
                {"text": "❌ Deny", "callback_data": f"deny:{run_id}"},
            ]],
        )

    if decision == "ALLOW":
        return (
            f"✅ <b>Allowed and paid</b>\n"
            f"State: <code>{_esc(sent.get('state'))}</code> · "
            f"Ref: <code>{_esc(sent.get('provider_reference') or '—')}</code>\n"
            f"Audit: <code>{_esc((sent.get('audit_hash') or '')[:16])}…</code>",
            None,
        )

    return (f"⚠️ Unexpected outcome: <code>{_esc(decision)}</code> ({_esc(reasons)})", None)


async def handle_message(
    api: TelegramAPI, backend: Backend, settings: Settings, message: dict
) -> None:
    chat_id = message["chat"]["id"]
    tid = message.get("from", {}).get("id")
    text = (message.get("text") or "").strip()
    if not text:
        return

    if settings.allowlist and str(tid) not in settings.allowlist:
        await api.send_message(chat_id, "This bot is not open to this account.")
        return

    if text in ("/start", "/start@" + settings.bot_username):
        await api.send_message(chat_id, WELCOME)
        return
    if text.startswith("/help"):
        await api.send_message(chat_id, HELP)
        return

    if LINK_RE.match(text):
        ok, detail = await backend.link_code(text, tid)
        if ok:
            await api.send_message(
                chat_id,
                f"✅ Linked to account <code>{_esc(detail)}</code>. "
                f"Now tell me what to buy.",
            )
        else:
            await api.send_message(chat_id, f"❌ Could not link: {_esc(detail)}")
        return

    user_id = await backend.whoami(tid)
    if not user_id:
        await api.send_message(
            chat_id,
            "This chat is not linked yet. Get a code from the web console's "
            "<b>Telegram</b> tab and send it to me.",
        )
        return

    if text.startswith("/status"):
        await api.send_message(chat_id, f"Linked to <code>{_esc(user_id)}</code>.")
        return

    scenario = "adversarial" if text.startswith("/attack") else "clean"
    instruction = (
        "Restock the office kitchen with coffee. Keep it under 5000 rupees."
        if scenario == "adversarial"
        else text
    )

    await api.send_message(chat_id, "🔍 Working… the agent is researching. This can take a bit.")
    try:
        summary = await backend.run(scenario, instruction, settings.default_budget)
    except Exception as exc:  # surfaced, never a fake success
        await api.send_message(chat_id, f"⚠️ The run failed: {_esc(exc)}")
        return

    text_out, buttons = format_decision(summary)
    if summary.get("decision") == "BLOCK":
        # Nothing was bought and there is nothing to confirm — fold the
        # attempted cart into the block message instead of announcing it
        # as if a purchase were about to happen.
        line = cart_oneline(summary)
        await api.send_message(
            chat_id, f"{text_out}\n\n{line}" if line else text_out, buttons=buttons
        )
    else:
        await api.send_message(chat_id, format_cart(summary))
        await api.send_message(chat_id, text_out, buttons=buttons)


async def handle_callback(api: TelegramAPI, backend: Backend, cq: dict) -> None:
    data = cq.get("data", "")
    msg = cq.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    await api.answer_callback_query(cq["id"])

    action, _, run_id = data.partition(":")
    if action == "deny":
        await api.send_message(chat_id, "❌ Denied. Nothing was charged.")
        return
    if action == "approve":
        await api.send_message(chat_id, "⏳ Approving…")
        try:
            summary = await backend.approve_run(run_id)
        except Exception as exc:
            await api.send_message(chat_id, f"⚠️ Approval failed: {_esc(exc)}")
            return
        text_out, _ = format_decision(summary)
        await api.send_message(chat_id, text_out)


async def handle_update(
    api: TelegramAPI, backend: Backend, settings: Settings, update: dict
) -> None:
    if "message" in update:
        await handle_message(api, backend, settings, update["message"])
    elif "callback_query" in update:
        await handle_callback(api, backend, update["callback_query"])
