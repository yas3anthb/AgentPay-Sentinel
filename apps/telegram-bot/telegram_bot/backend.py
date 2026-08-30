"""Calls into the AgentPay services. The bot decides nothing here — it asks
the control plane who a Telegram user is, asks the simulator to run the agent,
and asks the gateway to grant an approval. Every verdict comes from Sentinel.
"""
from __future__ import annotations

import logging

import httpx

from telegram_bot.config import Settings

log = logging.getLogger("telegram_bot.backend")


class Backend:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self._admin = {"X-Admin-Key": settings.admin_api_key, "X-Admin-Id": "telegram-bot"}

    # --- identity (control plane) --------------------------------------

    async def whoami(self, telegram_id: int | str) -> str | None:
        """Which AgentPay account is this Telegram id linked to, if any."""
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(
                f"{self.s.control_plane_url}/v1/admin/telegram/whoami/{telegram_id}",
                headers=self._admin,
            )
        if r.status_code != 200:
            return None
        body = r.json()
        return body.get("user_id") if body.get("linked") else None

    async def link_code(self, code: str, telegram_id: int | str) -> tuple[bool, str]:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(
                f"{self.s.control_plane_url}/v1/admin/telegram/link",
                headers=self._admin,
                json={"code": code.strip().upper(), "telegram_id": str(telegram_id)},
            )
        if r.status_code == 200:
            return True, r.json().get("user_id", "")
        detail = r.json().get("detail", f"HTTP {r.status_code}") if r.content else f"HTTP {r.status_code}"
        return False, str(detail)

    # --- the agent run (simulator) -----------------------------------

    async def run(self, scenario: str, instruction: str, budget: str) -> dict:
        path = "/simulate/adversarial" if scenario == "adversarial" else "/simulate/clean-purchase"
        async with httpx.AsyncClient(timeout=self.s.request_timeout_seconds) as c:
            r = await c.post(
                f"{self.s.simulator_url}{path}",
                json={"instruction": instruction, "budget": budget},
            )
        r.raise_for_status()
        return r.json()

    async def approve_run(self, run_id: str) -> dict:
        async with httpx.AsyncClient(timeout=self.s.request_timeout_seconds) as c:
            r = await c.post(f"{self.s.simulator_url}/simulate/{run_id}/approve")
        r.raise_for_status()
        return r.json()
