"""AgentPay Sentinel — live enforcement dashboard.

Reads the gateway's own read-only endpoints. It renders the pipeline the way
the system actually works: request → signals → OPA decision → reason codes →
audit chain, with the risk engine's signals shown as evidence rather than as a
verdict.
"""
from __future__ import annotations

import os
import time
from datetime import datetime

import httpx
import pandas as pd
import streamlit as st

GATEWAY = os.getenv("GATEWAY_URL", "http://localhost:8080")
REFRESH_SECONDS = 5

DECISION_COLOUR = {
    "ALLOW": "#1a7f37",
    "BLOCK": "#b42318",
    "REQUIRE_APPROVAL": "#b54708",
}
STATE_COLOUR = {
    "CONFIRMED": "#1a7f37",
    "AUTHORIZED": "#0b6bcb",
    "SUBMITTED": "#0b6bcb",
    "CREATED": "#5f6b7a",
    "FAILED": "#b42318",
    "TIMEOUT": "#b54708",
    "UNKNOWN": "#b54708",
    "EXPIRED": "#5f6b7a",
}

st.set_page_config(page_title="AgentPay Sentinel", page_icon="🛡️", layout="wide")


@st.cache_data(ttl=REFRESH_SECONDS)
def fetch(path: str, params: dict | None = None) -> dict:
    try:
        response = httpx.get(f"{GATEWAY}{path}", params=params, timeout=6.0)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return {"_error": str(exc)}


def badge(text: str, colour: str) -> str:
    return (
        f"<span style='background:{colour};color:#fff;padding:2px 9px;"
        f"border-radius:11px;font-size:0.78rem;font-weight:600;"
        f"white-space:nowrap'>{text}</span>"
    )


st.title("🛡️ AgentPay Sentinel")
st.caption(
    "Runtime policy-enforcement gateway between an AI shopping agent and a payment "
    "provider. Deny-by-default. OPA is the only Policy Decision Point — the risk "
    "engine emits signals, never verdicts."
)

health = fetch("/readyz")
cols = st.columns([1, 1, 1, 3])
if "_error" in health:
    cols[0].error("gateway unreachable")
    st.stop()
cols[0].metric("Gateway", "ready" if health.get("ready") else "degraded")
cols[1].metric("OPA (PDP)", health.get("checks", {}).get("opa", "?"))
cols[2].metric("Policy", health.get("policy_version", "?"))

transactions = fetch("/v1/transactions", {"limit": 100}).get("transactions", [])
events = fetch("/v1/audit/events", {"limit": 200}).get("events", [])
chain = fetch("/v1/audit/verify")

# --- headline counters -----------------------------------------------------

allowed = sum(1 for t in transactions if t["decision"] == "ALLOW")
blocked = sum(1 for t in transactions if t["decision"] == "BLOCK")
approvals = sum(1 for t in transactions if t["decision"] == "REQUIRE_APPROVAL")
confirmed = sum(1 for t in transactions if t["state"] == "CONFIRMED")
unresolved = sum(1 for t in transactions if t["state"] in {"UNKNOWN", "TIMEOUT"})

m = st.columns(6)
m[0].metric("Transactions", len(transactions))
m[1].metric("Allowed", allowed)
m[2].metric("Blocked", blocked)
m[3].metric("Awaiting approval", approvals)
m[4].metric("Settled", confirmed)
m[5].metric("Unresolved", unresolved, help="TIMEOUT/UNKNOWN awaiting reconciliation")

if chain.get("valid"):
    st.success(
        f"Audit chain intact across {chain.get('events_checked', 0)} events · "
        f"head {str(chain.get('head_hash',''))[:24]}… · "
        f"{chain.get('claim','')}",
        icon="🔗",
    )
else:
    st.error(
        f"AUDIT CHAIN BROKEN at seq {chain.get('broken_at_seq')} "
        f"(event {chain.get('broken_event_id')})",
        icon="⚠️",
    )

st.divider()

left, right = st.columns([5, 4])

# --- decision feed ---------------------------------------------------------

with left:
    st.subheader("Decision feed")
    if not transactions:
        st.info("No transactions yet. Run `make demo-clean` or `make demo-injection`.")
    for txn in transactions[:25]:
        when = datetime.fromisoformat(txn["created_at"]).strftime("%H:%M:%S")
        header = (
            f"{when} · {txn['amount']} {txn['currency']} → {txn['merchant_id']} "
            f"· {txn['decision']}"
        )
        with st.expander(header, expanded=False):
            head = st.columns([1, 1, 2])
            head[0].markdown(
                badge(txn["decision"], DECISION_COLOUR.get(txn["decision"], "#5f6b7a")),
                unsafe_allow_html=True,
            )
            head[1].markdown(
                badge(txn["state"], STATE_COLOUR.get(txn["state"], "#5f6b7a")),
                unsafe_allow_html=True,
            )
            head[2].markdown(
                f"**risk {txn.get('weighted_score', 0)}** / 100 · policy "
                f"`{txn['policy_version']}`"
            )
            st.markdown("**Reason codes**")
            st.code("\n".join(txn["reason_codes"]) or "-", language="text")

            event = next(
                (
                    e
                    for e in events
                    if e["payment_authorization_id"] == txn["payment_authorization_id"]
                    and e["event_type"].startswith("decision.")
                ),
                None,
            )
            if event:
                signals = (event.get("risk") or {}).get("signals", {})
                if signals:
                    st.markdown("**Risk signals** *(evidence, not a decision)*")
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {"signal": k, "value": v}
                                for k, v in signals.items()
                                if isinstance(v, (int, float))
                            ]
                        ),
                        hide_index=True,
                        use_container_width=True,
                    )
                analysis = (event.get("payload") or {}).get("analysis", {})
                evidence = analysis.get("evidence") or []
                if evidence:
                    st.markdown("**Why the analyzer flagged it**")
                    for item in evidence:
                        st.markdown(
                            f"- `{item['layer']}` **{item['label']}** in "
                            f"`{item['field']}` — {item['why']}"
                        )
                        if item.get("excerpt"):
                            st.caption(f"“…{item['excerpt']}…”")
                if analysis.get("classifier_degraded"):
                    st.warning(
                        "Classifier was unavailable "
                        f"({analysis.get('classifier_degraded_reason')}). "
                        "The policy fails closed on this.",
                        icon="🚧",
                    )
                st.caption(
                    f"audit event `{event['event_id']}` · hash "
                    f"`{event['event_hash'][:32]}…` chains to "
                    f"`{event['prev_hash'][:16]}…`"
                )
            if txn.get("provider_reference"):
                st.caption(f"provider reference `{txn['provider_reference']}`")

# --- pipeline + audit ------------------------------------------------------

with right:
    st.subheader("Enforcement pipeline")
    st.markdown(
        """
1. **Identity & request integrity** — delegation JWT, agent scope, revocation set
2. **Canonical transaction** — typed intent; free text quarantined as untrusted
3. **Content security analyzer** — regex rules + OpenAI classifier + source trust
4. **Risk engine** — signals only · `R = 35·I + 25·P + 20·B + 10·M + 10·V`
5. **OPA (PDP)** — the *only* component that emits ALLOW / APPROVAL / BLOCK
6. **Payment authorization** — scoped single-use token, explicit state machine
7. **Audit** — hash-chained, every decision, not just the blocks
        """
    )

    st.subheader("Reason codes seen")
    counts: dict[str, int] = {}
    for txn in transactions:
        for code in txn["reason_codes"]:
            counts[code] = counts.get(code, 0) + 1
    if counts:
        frame = pd.DataFrame(
            sorted(counts.items(), key=lambda kv: -kv[1]), columns=["reason_code", "count"]
        )
        st.dataframe(frame, hide_index=True, use_container_width=True)
    else:
        st.caption("none yet")

    st.subheader("Audit chain")
    if events:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "seq": e["seq"],
                        "type": e["event_type"],
                        "decision": e["decision"] or "-",
                        "hash": e["event_hash"][:16] + "…",
                    }
                    for e in events[:40]
                ]
            ),
            hide_index=True,
            use_container_width=True,
            height=340,
        )

st.divider()
controls = st.columns([1, 1, 4])
auto = controls[0].toggle("Live", value=True, help=f"Re-read the gateway every {REFRESH_SECONDS}s")
if controls[1].button("Refresh now"):
    st.cache_data.clear()
    st.rerun()
controls[2].caption(
    f"gateway {GATEWAY} · the audit chain is tamper-evident within the current trust "
    "boundary, not tamper-proof."
)

if auto:
    # No extra dependency: sleep out the interval, drop the cache, rerun.
    time.sleep(REFRESH_SECONDS)
    st.cache_data.clear()
    st.rerun()
