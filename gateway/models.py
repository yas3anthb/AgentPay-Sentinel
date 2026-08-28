"""Persistence models: transactions, policies/agents (control plane), audit log."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class AgentRegistration(Base):
    """Control plane: which agents exist and what they are scoped to do."""

    __tablename__ = "agent_registrations"

    agent_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(128), index=True)
    display_name: Mapped[str] = mapped_column(String(256), default="")
    allowed_scopes: Mapped[list] = mapped_column(JSON, default=list)
    allowed_merchant_categories: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SpendingPolicy(Base):
    """Control plane: the versioned budget/merchant policy bound to a delegation."""

    __tablename__ = "spending_policies"

    delegation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    agent_id: Mapped[str] = mapped_column(String(128), index=True)
    policy_version: Mapped[str] = mapped_column(String(32), default="v1.4.2")

    per_transaction_limit: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    daily_limit: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    allowed_merchants: Mapped[list] = mapped_column(JSON, default=list)
    blocked_merchants: Mapped[list] = mapped_column(JSON, default=list)
    require_verified_merchant: Mapped[bool] = mapped_column(Boolean, default=True)
    approval_threshold: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    max_transactions_per_hour: Mapped[int] = mapped_column(default=10)

    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Merchant(Base):
    __tablename__ = "merchants"

    merchant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(256), default="")
    category: Mapped[str] = mapped_column(String(64), default="general")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_score: Mapped[float] = mapped_column(default=0.2)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Transaction(Base):
    """One row per payment authorization attempt, carrying the state machine."""

    __tablename__ = "transactions"
    # One *authorized* transaction per idempotency key, enforced in the database
    # as well as in Redis. Blocked attempts are exempt: every rejected replay
    # still deserves its own row in the record, and a partial index is how you
    # get both properties at once.
    __table_args__ = (
        Index(
            "uq_user_idempotency_authorized",
            "user_id",
            "idempotency_key",
            unique=True,
            sqlite_where=text("decision <> 'BLOCK'"),
            postgresql_where=text("decision <> 'BLOCK'"),
        ),
    )

    payment_authorization_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)

    user_id: Mapped[str] = mapped_column(String(128), index=True)
    agent_id: Mapped[str] = mapped_column(String(128), index=True)
    delegation_id: Mapped[str] = mapped_column(String(128), index=True)
    merchant_id: Mapped[str] = mapped_column(String(128), index=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    cart_hash: Mapped[str] = mapped_column(String(64))

    decision: Mapped[str] = mapped_column(String(24))
    reason_codes: Mapped[list] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String(24), default="CREATED", index=True)
    risk: Mapped[dict] = mapped_column(JSON, default=dict)
    policy_version: Mapped[str] = mapped_column(String(32))

    token_jti: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_uses: Mapped[int] = mapped_column(default=0)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    provider_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    stored_response: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class AuditEvent(Base):
    """Append-only, hash-chained. Tamper-EVIDENT within this trust boundary."""

    __tablename__ = "audit_events"

    # SQLite only autoincrements a plain INTEGER PRIMARY KEY, so the BIGINT we
    # want on Postgres has to be varianted for the dev/test database.
    seq: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)

    payment_authorization_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    decision: Mapped[str | None] = mapped_column(String(24), nullable=True)
    reason_codes: Mapped[list] = mapped_column(JSON, default=list)
    risk: Mapped[dict] = mapped_column(JSON, default=dict)
    policy_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    prev_hash: Mapped[str] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
