"""Telegram account linking for the demo bot.

A Telegram user id on its own is a weak identity, so it is bound to a real
AgentPay account through a one-time code the user copies from the web console:

    web console (logged in as user_ada)  ->  issues LINK-7F3K9Q
    user sends LINK-7F3K9Q to the bot    ->  bot calls /v1/admin/telegram/link
    control plane stores telegram_id -> user_id, marks the code spent

Codes are single-use and expire after 10 minutes. Nothing here can move money;
it only resolves "which account is this Telegram user acting as".
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, String, select
from sqlalchemy.orm import Mapped, mapped_column

from gateway.db import session_scope
from gateway.models import Base

CODE_TTL = timedelta(minutes=10)
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous 0/O/1/I/L


class TelegramLink(Base):
    __tablename__ = "telegram_links"

    telegram_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class TelegramLinkCode(Base):
    __tablename__ = "telegram_link_codes"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _mask(telegram_id: str) -> str:
    if len(telegram_id) <= 4:
        return "*" * len(telegram_id)
    return f"{telegram_id[:2]}{'*' * (len(telegram_id) - 4)}{telegram_id[-2:]}"


async def issue_code(user_id: str) -> dict:
    """Mint a fresh one-time link code for an account. Any earlier unused code
    for the same account is dropped so only the latest one works."""
    code = "LINK-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
    now = datetime.now(timezone.utc)
    async with session_scope() as s:
        stale = (
            await s.execute(
                select(TelegramLinkCode).where(
                    TelegramLinkCode.user_id == user_id,
                    TelegramLinkCode.used_at.is_(None),
                )
            )
        ).scalars().all()
        for row in stale:
            await s.delete(row)
        s.add(TelegramLinkCode(code=code, user_id=user_id, created_at=now))
    return {
        "code": code,
        "expires_at": (now + CODE_TTL).isoformat(),
        "expires_in_seconds": int(CODE_TTL.total_seconds()),
    }


class LinkError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


async def redeem_code(code: str, telegram_id: str) -> dict:
    """Bind a Telegram id to the account the code was issued for. Raises
    LinkError(404 / 409 / 410) on an unknown, spent, or expired code."""
    code = code.strip().upper()
    telegram_id = str(telegram_id).strip()
    async with session_scope() as s:
        row = await s.get(TelegramLinkCode, code)
        if row is None:
            raise LinkError(404, "unknown link code")
        if row.used_at is not None:
            raise LinkError(409, "link code already used")
        if datetime.now(timezone.utc) - _aware(row.created_at) > CODE_TTL:
            raise LinkError(410, "link code expired")

        row.used_at = datetime.now(timezone.utc)
        await s.merge(
            TelegramLink(
                telegram_id=telegram_id,
                user_id=row.user_id,
                linked_at=datetime.now(timezone.utc),
            )
        )
        user_id = row.user_id
    return {"status": "linked", "user_id": user_id, "telegram_id_masked": _mask(telegram_id)}


async def resolve_user(telegram_id: str) -> str | None:
    async with session_scope() as s:
        row = await s.get(TelegramLink, str(telegram_id).strip())
    return row.user_id if row else None


async def status_for_user(user_id: str) -> dict:
    async with session_scope() as s:
        row = (
            await s.execute(select(TelegramLink).where(TelegramLink.user_id == user_id))
        ).scalars().first()
    if row is None:
        return {"linked": False}
    return {
        "linked": True,
        "telegram_id_masked": _mask(row.telegram_id),
        "linked_at": _aware(row.linked_at).isoformat(),
    }


async def unlink_user(user_id: str) -> dict:
    async with session_scope() as s:
        rows = (
            await s.execute(select(TelegramLink).where(TelegramLink.user_id == user_id))
        ).scalars().all()
        for row in rows:
            await s.delete(row)
    return {"status": "unlinked", "removed": len(rows)}
