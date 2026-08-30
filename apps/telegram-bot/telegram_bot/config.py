"""Bot configuration. Demo only.

The bot holds a Telegram token and an admin key for the control-plane *link*
endpoints — nothing that can move money. It is a client of the same APIs the
web console uses.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str = ""
    bot_username: str = ""
    mode: str = "polling"  # polling | webhook
    webhook_url: str = ""
    webhook_secret_path: str = "tg"

    gateway_url: str = "http://localhost:8080"
    simulator_url: str = "http://localhost:9200"
    control_plane_url: str = "http://localhost:8090"
    admin_api_key: str = "dev-admin-key"

    # Optional hard allow-list of Telegram ids, comma-separated. Empty = anyone
    # who has completed the link flow.
    allowlist: tuple[str, ...] = ()

    default_budget: str = "5000.00"
    request_timeout_seconds: float = 120.0

    def require_token(self) -> str:
        if not self.bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
        return self.bot_token


@lru_cache
def get_settings() -> Settings:
    raw_allow = os.getenv("TELEGRAM_ALLOWLIST", "").strip()
    return Settings(
        bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        bot_username=os.getenv("TELEGRAM_BOT_USERNAME", ""),
        mode=os.getenv("TELEGRAM_MODE", "polling").strip().lower(),
        webhook_url=os.getenv("TELEGRAM_WEBHOOK_URL", ""),
        webhook_secret_path=os.getenv("TELEGRAM_WEBHOOK_SECRET_PATH", "tg"),
        gateway_url=os.getenv("GATEWAY_URL", "http://localhost:8080"),
        simulator_url=os.getenv("SIMULATOR_URL", "http://localhost:9200"),
        control_plane_url=os.getenv("CONTROL_PLANE_URL", "http://localhost:8090"),
        admin_api_key=os.getenv("ADMIN_API_KEY", "dev-admin-key"),
        allowlist=tuple(x.strip() for x in raw_allow.split(",") if x.strip()),
        default_budget=os.getenv("TELEGRAM_DEFAULT_BUDGET", "5000.00"),
        request_timeout_seconds=float(os.getenv("TELEGRAM_REQUEST_TIMEOUT", "120")),
    )
