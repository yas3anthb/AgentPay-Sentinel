"""Edge rate limiting — a coarse request ceiling in front of the pipeline.

This is **not** the policy's `VELOCITY_LIMIT_EXCEEDED` rule. That one is a
deliberate policy decision about how fast an agent may *authorize spend*, it
runs inside OPA, and it counts settled transactions. This is infrastructure:
a per-agent / per-delegation cap on how many payment-intent requests may even
*enter* the pipeline per minute, checked before the expensive stages — the
content analyzer and its LLM call in particular — so a compromised or looping
agent cannot turn the classifier into a cost-amplification target.

Failure policy is the opposite of the rest of the gateway: this fails **open**.
Identity has already been verified by the time we get here and the policy
engine still runs on every request, so the security controls are intact
without this. A throttle that failed closed would turn a brief Redis blip into
"every payment blocked", which is exactly the availability failure this control
is meant to avoid, not cause.
"""
from __future__ import annotations

import logging

from gateway.config import get_settings
from gateway.store import get_store

log = logging.getLogger("agentpay.ratelimit")

_WINDOW_SECONDS = 60


class RateLimitError(Exception):
    """Raised when a caller is over its edge request ceiling. Terminal (BLOCK),
    but with its own reason code so the audit log never confuses an
    infrastructure throttle with a policy verdict."""

    reason_code = "RATE_LIMIT_EXCEEDED"

    def __init__(self, scope: str, limit: int) -> None:
        super().__init__(f"edge rate limit exceeded for {scope} ({limit}/min)")
        self.scope = scope
        self.limit = limit
        self.retry_after_seconds = _WINDOW_SECONDS


async def enforce_edge_rate_limit(agent_id: str, delegation_id: str) -> None:
    """Check the per-agent and per-delegation request ceilings, then record
    this request. Raises :class:`RateLimitError` if either ceiling is already
    met. A store error is logged and swallowed — see the module docstring."""
    settings = get_settings()
    if not settings.edge_rate_limit_enabled:
        return

    store = get_store()
    checks = (
        (f"agentpay:rl:agent:{agent_id}", settings.edge_rate_limit_agent_per_min, f"agent {agent_id}"),
        (
            f"agentpay:rl:deleg:{delegation_id}",
            settings.edge_rate_limit_delegation_per_min,
            f"delegation {delegation_id}",
        ),
    )

    try:
        # Check every ceiling before recording anything, so a rejected request
        # does not itself inflate the window it was rejected against.
        for key, limit, scope in checks:
            if limit > 0 and await store.zcount_window(key, _WINDOW_SECONDS) >= limit:
                raise RateLimitError(scope, limit)
        for key, limit, _ in checks:
            if limit > 0:
                await store.zadd_window(key, _WINDOW_SECONDS)
    except RateLimitError:
        raise
    except Exception as exc:  # fail open — availability over strictness, here only
        log.warning("edge rate limit check failed, allowing request: %s", exc)
