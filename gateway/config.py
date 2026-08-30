"""Runtime configuration. Everything is env-driven; no secrets in source."""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # AGENTPAY_ENV_FILE lets the test suite point at a file that does not
    # exist, so a developer's local .env can never change a test's outcome.
    model_config = SettingsConfigDict(
        env_file=os.getenv("AGENTPAY_ENV_FILE", ".env"), extra="ignore"
    )

    # --- service ---
    service_name: str = "agentpay-sentinel"
    environment: str = "dev"

    # --- policy ---
    policy_version: str = "v1.4.2"
    # Single source of truth lives in Rego. This value is only used for
    # display/telemetry so the API can report which bundle it expects.

    # --- identity ---
    # The gateway holds only the delegation PUBLIC key: it verifies inbound
    # delegation JWTs, it never mints them (that is the control plane's job,
    # and only the control plane has the private half).
    jwt_public_key_path: str = "keys/delegation_public.pem"
    # Present in dev/test so scripts/tests can mint tokens locally; NOT mounted
    # into the gateway container in Compose. `mint_delegation_token` throws if
    # the file is absent, which is the correct behaviour for a prod gateway.
    jwt_private_key_path: str = "keys/delegation_private.pem"
    jwt_algorithm: str = "RS256"
    jwt_issuer: str = "agentpay-control-plane"
    jwt_audience: str = "agentpay-sentinel"

    # --- payment-token signing (a SEPARATE keypair from delegation) ---
    # The gateway legitimately issues scoped, single-use payment tokens and
    # human-approval tokens mid-pipeline. Those use their own keypair so the
    # delegation-signing trust domain and the payment-signing trust domain are
    # cryptographically distinct. The mock provider verifies with the public
    # half.
    payment_signing_private_key_path: str = "keys/payment_private.pem"
    payment_signing_public_key_path: str = "keys/payment_public.pem"

    # --- dependencies ---
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "postgresql+asyncpg://agentpay:agentpay@localhost:5432/agentpay"
    # Independent append-only store for audit-chain checkpoints. Separate host
    # AND separate credentials on purpose — see gateway/checkpoint.py. Empty =
    # not configured (the chain is then tamper-evident within one trust
    # boundary only).
    checkpoint_database_url: str = ""
    opa_url: str = "http://localhost:8181"
    opa_decision_path: str = "agentpay/decision/result"
    provider_url: str = "http://localhost:9100"

    # --- OpenAI classifier ---
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    # Tight on purpose: the deterministic rule + similarity layers are the floor,
    # so a slow classifier should degrade fast rather than hold up a payment.
    openai_timeout_seconds: float = 4.0
    # Fail-closed: if the classifier errors or times out we emit a BLOCK-grade
    # signal rather than waving the transaction through.
    classifier_fail_closed: bool = True
    # Set true to skip the network call entirely (offline demos / CI).
    classifier_offline: bool = False
    # Circuit breaker (see gateway/analyzer/llm.py): after this many consecutive
    # transport failures the classifier call is skipped for the cooldown, so an
    # OpenAI outage stops costing every request a full timeout.
    classifier_circuit_failures: int = 4
    classifier_circuit_cooldown_seconds: float = 30.0
    # DEV ONLY. Lets the PDP proceed when the classifier is unavailable instead
    # of failing closed. Never enable this anywhere real: it turns off the
    # single control that keeps an outage from becoming an open door.
    allow_degraded_classifier: bool = False
    # Graceful degradation, safe to run in production. When the LLM classifier
    # is unavailable AND the deterministic layers (rules + similarity) found
    # nothing, route to REQUIRE_APPROVAL instead of an outright BLOCK. Nothing
    # is authorized without a verdict — the verdict just comes from a human.
    # Turns a classifier outage from "every payment declined" into "every
    # payment waits for review". If the deterministic layers DID flag the
    # content, the block still stands.
    degraded_classifier_requires_review: bool = True

    # --- payment authorization ---
    token_ttl_seconds: int = 300
    provider_timeout_seconds: float = 5.0
    fingerprint_window_seconds: int = 300
    idempotency_ttl_seconds: int = 86400
    lock_ttl_seconds: int = 10

    # --- revocation ---
    revocation_cache_ttl_seconds: int = 45

    # --- edge rate limiting (see gateway/ratelimit.py) ---
    # A coarse per-minute request ceiling in front of the pipeline, checked
    # before the analyzer/LLM call. Distinct from the policy's velocity rule.
    # Fails open. Set a ceiling to 0 to disable just that scope.
    edge_rate_limit_enabled: bool = True
    edge_rate_limit_agent_per_min: int = 90
    edge_rate_limit_delegation_per_min: int = 150


@lru_cache
def get_settings() -> Settings:
    return Settings()
