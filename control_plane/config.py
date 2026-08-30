"""Control-plane configuration.

Separate settings object from the gateway's on purpose: this service lives in a
different trust domain. It is the only component that holds the delegation
*private* key and the only one that mints delegation tokens. The enforcement
gateway holds just the public half and can verify, never issue.
"""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("AGENTPAY_ENV_FILE", ".env"), extra="ignore"
    )

    service_name: str = "agentpay-control-plane"
    environment: str = "dev"
    policy_version: str = "v1.4.2"

    # The registry the gateway reads from. Same database; the control plane
    # writes the agent / policy / merchant tables, the gateway only reads them.
    database_url: str = "postgresql+asyncpg://agentpay:agentpay@localhost:5432/agentpay"

    # Shared secret on every mutating call. There is no default that works:
    # a blank key makes the control plane refuse to start outside dev/test.
    admin_api_key: str = "dev-admin-key"

    # The delegation signing key. Present ONLY in this service.
    delegation_private_key_path: str = "keys/delegation_private.pem"
    delegation_public_key_path: str = "keys/delegation_public.pem"
    jwt_algorithm: str = "RS256"
    jwt_issuer: str = "agentpay-control-plane"
    jwt_audience: str = "agentpay-sentinel"

    redis_url: str = "redis://localhost:6379/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
