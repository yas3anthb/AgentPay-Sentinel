"""A tiny async Telegram Bot API client — just what this demo bot needs.

No third-party Telegram library: it's one HTTPS endpoint with JSON bodies. The
token is read once, kept in memory, and never logged.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger("telegram_bot.api")

# httpx logs the full request URL at INFO, and every Bot API URL contains the
# bot token. Keep those out of the container logs.
logging.getLogger("httpx").setLevel(logging.WARNING)


class TelegramAPI:
    def __init__(self, token: str) -> None:
        self._base = f"https://api.telegram.org/bot{token}"
        self._client = httpx.AsyncClient(timeout=65.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def _call(self, method: str, **params: Any) -> Any:
        r = await self._client.post(f"{self._base}/{method}", json=params)
        body = r.json()
        if not body.get("ok"):
            log.warning("telegram %s failed: %s", method, body.get("description"))
            return None
        return body.get("result")

    async def get_me(self) -> dict | None:
        return await self._call("getMe")

    async def get_updates(self, offset: int, timeout: int = 50) -> list[dict]:
        res = await self._call(
            "getUpdates",
            offset=offset,
            timeout=timeout,
            allowed_updates=["message", "callback_query"],
        )
        return res or []

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        *,
        buttons: list[list[dict]] | None = None,
        parse_mode: str = "HTML",
    ) -> dict | None:
        params: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if buttons:
            params["reply_markup"] = {"inline_keyboard": buttons}
        return await self._call("sendMessage", **params)

    async def edit_message_text(
        self, chat_id: int | str, message_id: int, text: str, *, parse_mode: str = "HTML"
    ) -> dict | None:
        return await self._call(
            "editMessageText",
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode=parse_mode,
            disable_web_page_preview=True,
        )

    async def answer_callback_query(self, callback_query_id: str, text: str = "") -> None:
        await self._call("answerCallbackQuery", callback_query_id=callback_query_id, text=text)

    async def set_webhook(self, url: str) -> Any:
        return await self._call("setWebhook", url=url, allowed_updates=["message", "callback_query"])

    async def delete_webhook(self) -> Any:
        return await self._call("deleteWebhook")
