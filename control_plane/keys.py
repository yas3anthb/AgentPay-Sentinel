"""Delegation-token issuance. This module is the reason the control plane is a
separate service: it holds the delegation *private* key, and nothing in the
enforcement gateway does. The gateway verifies with the public half only.
"""
from __future__ import annotations

import pathlib
import time

import jwt

from control_plane.config import get_settings

REQUIRED_SCOPE = "payments:authorize"


def _private_key() -> str:
    path = pathlib.Path(get_settings().delegation_private_key_path)
    if not path.exists():
        raise RuntimeError(
            f"delegation private key missing at {path}; the control plane cannot "
            "mint tokens without it (run scripts/gen_keys.py or mount the volume)"
        )
    return path.read_text()


def sign_delegation_token(
    *,
    agent_id: str,
    user_id: str,
    delegation_id: str,
    scopes: list[str] | None = None,
    ttl_seconds: int = 3600,
) -> str:
    s = get_settings()
    now = int(time.time())
    return jwt.encode(
        {
            "iss": s.jwt_issuer,
            "aud": s.jwt_audience,
            "sub": user_id,
            "agent_id": agent_id,
            "delegation_id": delegation_id,
            "scopes": scopes if scopes is not None else [REQUIRED_SCOPE],
            "iat": now,
            "exp": now + ttl_seconds,
            "jti": f"jti_{now}_{delegation_id}",
        },
        _private_key(),
        algorithm=s.jwt_algorithm,
    )
