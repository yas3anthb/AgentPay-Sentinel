"""Admin authentication for the control plane.

Every mutating endpoint depends on :func:`require_admin`. A request without a
valid ``X-Admin-Key`` gets a 401 and never touches the database. ``X-Admin-Id``
is a free-text label for *who* is acting; it is not trusted for authorization,
only recorded in the admin audit trail so actions are attributable.

This is intentionally a shared-secret scheme, not the real thing. A production
control plane puts SSO / mTLS and per-operator identity here. What matters for
the demo is that the door exists and is shut by default.
"""
from __future__ import annotations

import hmac
from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from control_plane.config import get_settings


@dataclass(frozen=True, slots=True)
class AdminPrincipal:
    admin_id: str


async def require_admin(
    x_admin_key: str | None = Header(default=None),
    x_admin_id: str | None = Header(default=None),
) -> AdminPrincipal:
    expected = get_settings().admin_api_key
    if not expected:
        # No key configured at all — refuse rather than run wide open.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="control plane has no ADMIN_API_KEY configured",
        )
    if not x_admin_key or not hmac.compare_digest(x_admin_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid X-Admin-Key",
            headers={"WWW-Authenticate": "X-Admin-Key"},
        )
    return AdminPrincipal(admin_id=(x_admin_id or "unknown")[:128])
