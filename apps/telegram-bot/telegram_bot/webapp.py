"""Webhook mode (deployed demo). Telegram POSTs updates to
`/{webhook_secret_path}`; everything else 404s. Also serves `/healthz`.

Long-polling (`telegram_bot.main`) is the default and needs no public URL —
prefer it for a laptop demo. This exists so a deployed bot does not have to
hold a long poll open.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from telegram_bot.api import TelegramAPI
from telegram_bot.backend import Backend
from telegram_bot.config import get_settings
from telegram_bot.handlers import handle_update

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("telegram_bot.webapp")

_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    api = TelegramAPI(s.require_token())
    _state["api"] = api
    _state["backend"] = Backend(s)
    _state["settings"] = s
    if s.webhook_url:
        await api.set_webhook(f"{s.webhook_url.rstrip('/')}/{s.webhook_secret_path}")
        log.info("webhook set to %s/%s", s.webhook_url.rstrip("/"), s.webhook_secret_path)
    yield
    await api.close()


app = FastAPI(title="AgentPay Sentinel Telegram bot", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "mode": "webhook"}


@app.post("/{path}")
async def webhook(path: str, request: Request) -> Response:
    s = _state["settings"]
    if path != s.webhook_secret_path:
        return Response(status_code=404)
    update = await request.json()
    try:
        await handle_update(_state["api"], _state["backend"], s, update)
    except Exception:
        log.exception("handler error")
    return Response(status_code=200)
