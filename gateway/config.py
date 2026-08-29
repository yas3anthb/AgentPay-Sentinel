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
    jwt_public_key_path: str = "keys/delegation_public.pem"
    jwt_private_key_path: str = "keys/delegation_private.pem"
    jwt_algorithm: str = "RS256"
    jwt_issuer: str = "agentpay-control-plane"
    jwt_audience: str = "agentpay-sentinel"

    # --- dependencies ---
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "postgresql+asyncpg://agentpay:agentpay@localhost:5432/agentpay"
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
    # DEV ONLY. Lets the PDP proceed when the classifier is unavailable instead
    # of failing closed. Never enable this anywhere real: it turns off the
    # single control that keeps an outage from becoming an open door.
    allow_degraded_classifier: bool = False

    # --- payment authorization ---
    token_ttl_seconds: int = 300
    provider_timeout_seconds: float = 5.0
    fingerprint_window_seconds: int = 300
    idempotency_ttl_seconds: int = 86400
    lock_ttl_seconds: int = 10

    # --- revocation ---
    revocation_cache_ttl_seconds: int = 45


@lru_cache
def get_settings() -> Settings:
    return Settings()
