# Availability & failure modes

The enforcement pipeline (`POST /v1/payment-intents`) depends on four external
components. This document states, for each, what happens when it is down and
what the recovery path is. The guiding rule is unchanged from the README:
**absence of a decision is never an implicit ALLOW.**

## Dependency graph (payment path)

```
request
  │
  ├─ 1 identity        needs: delegation PUBLIC key (file), Redis (revocation set)
  ├─   edge rate limit needs: Redis            — FAILS OPEN (see gateway/ratelimit.py)
  ├─ 2 canonical       pure function, no I/O
  ├─ 3 analyzer        needs: OpenAI (classifier) — degrades, never blocks the request itself
  ├─ 4 risk            pure function, no I/O
  ├─ 5 pdp             needs: OPA
  ├─ 6 authorization   needs: Postgres (idempotency, state), payment SIGNING key, provider
  └─ 7 audit           needs: Postgres; optionally the checkpoint DB (independent)
```

## What each outage does

| Component | On failure | Reason code | Recovery |
|---|---|---|---|
| **Redis** (revocation) | Request **BLOCKED** — a delegation's revocation status cannot be confirmed | `REVOCATION_CHECK_UNAVAILABLE` | Redis is single-node in this build; RTO = Redis restart. A read replica for the revocation set is the first HA step. |
| **Redis** (edge rate limit) | Request **proceeds** — the throttle fails open on purpose | — | The throttle is defence-in-depth; identity + policy still run. |
| **Redis** (idempotency lock) | Request **BLOCKED** | `CONCURRENT_REQUEST_IN_FLIGHT` / lock `TimeoutError` | As above. |
| **OpenAI classifier** | `classifier_degraded = true`. The rule + similarity layers still produce a `deterministic_confidence`. **If they flagged the content → BLOCK** (`CLASSIFIER_UNAVAILABLE_FAIL_CLOSED`). **If they are clean → REQUIRE_APPROVAL** (`CLASSIFIER_UNAVAILABLE_HUMAN_REVIEW`) — an outage becomes "every payment waits for a human", not "every payment declined". `DEGRADED_CLASSIFIER_REQUIRES_REVIEW=false` restores the unconditional block; `allow_degraded_classifier` (dev-only) lets it ALLOW. | `CLASSIFIER_UNAVAILABLE_FAIL_CLOSED` / `_HUMAN_REVIEW` | The **circuit breaker** (`gateway/analyzer/llm.py`) opens after `classifier_circuit_failures` consecutive transport failures and skips the call for `classifier_circuit_cooldown_seconds`, so requests stop paying the timeout. One trial request probes recovery. |
| **OPA** | Request **BLOCKED** | `PDP_UNAVAILABLE_FAIL_CLOSED` | OPA holds no state — run it as a sidecar in the same pod so this is a localhost call, not a network hop. RTO = container restart. |
| **Postgres** | Request **BLOCKED** (idempotency check / persistence / audit write fail; the unhandled-exception handler returns a BLOCK) | `INTERNAL_ERROR_FAIL_CLOSED` | Postgres is single-node here. A primary + synchronous standby is the first HA step; audit is append-only so it tolerates a read replica for verification. |
| **Payment provider** | Payment resolves to `UNKNOWN`, **not** success. Never auto-retried. | — | `POST /v1/reconcile` queries the provider and resolves to `CONFIRMED` or `FAILED`. |
| **Checkpoint DB** (see `gateway/checkpoint.py`) | Anchoring is skipped; the main audit chain is unaffected | — | Independent credentials/host on purpose; a checkpoint outage never touches the payment path. |
| **Event relay** | No live pipeline visualisation | — | Read-only, out of the payment path; the gateway does not depend on it. |

## The one lever

`ALLOW_DEGRADED_CLASSIFIER=true` feeds `context.allow_degraded_classifier` into
OPA, which lets a transaction proceed when the LLM classifier is unavailable
(the deterministic layers still run and still gate). It is the only switch that
relaxes a fail-closed rule. It is **dev-only** and must never be set where real
money moves — see the README.

## Latency

`scripts/bench.py` measures the end-to-end and per-stage latency distribution
against a running stack and writes the table to [`latency.md`](latency.md). The
classifier call dominates the `analyzer` stage when it is live; the tight
`openai_timeout_seconds` (default 4s) plus the circuit breaker bound its
worst case.
