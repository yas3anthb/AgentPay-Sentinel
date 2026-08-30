"""Entry point. Long-polling by default (no public URL needed — good for a
laptop demo); webhook mode is available for a deployed demo.

DEMO ONLY. The bot holds a Telegram token and the control-plane admin key for
the *link* endpoints. It cannot authorize, block, or modify a payment.
"""
from __future__ import annotations

import asyncio
import logging

from telegram_bot.api import TelegramAPI
from telegram_bot.backend import Backend
from telegram_bot.config import get_settings
from telegram_bot.handlers import handle_update

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
log = logging.getLogger("telegram_bot")


async def _poll_loop() -> None:
    settings = get_settings()
    api = TelegramAPI(settings.require_token())
    backend = Backend(settings)

    me = await api.get_me()
    if not me:
        raise RuntimeError("getMe failed — is TELEGRAM_BOT_TOKEN valid?")
    log.info("bot @%s online (polling)", me.get("username"))
    await api.delete_webhook()  # ensure polling is not fighting a stale webhook

    offset = 0
    try:
        while True:
            try:
                updates = await api.get_updates(offset, timeout=50)
            except Exception as exc:  # network blip — back off and retry
                log.warning("getUpdates failed: %s", exc)
                await asyncio.sleep(3)
                continue
            for update in updates:
                offset = max(offset, update["update_id"] + 1)
                try:
                    await handle_update(api, backend, settings, update)
                except Exception:
                    log.exception("handler error on update %s", update.get("update_id"))
    finally:
        await api.close()


def main() -> None:
    settings = get_settings()
    if settings.mode == "webhook":
        # Deployed mode: run the FastAPI app in webapp.py under uvicorn instead.
        raise SystemExit(
            "TELEGRAM_MODE=webhook: run `uvicorn telegram_bot.webapp:app` instead of this."
        )
    asyncio.run(_poll_loop())


if __name__ == "__main__":
    main()
