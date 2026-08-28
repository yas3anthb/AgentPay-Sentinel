"""Canonical wire schemas.

Design rule: the *payment instruction* is always a typed object. Free-form text
(merchant content, the agent's stated `purpose`, raw tool arguments) is carried
alongside as explicitly-labelled untrusted data and never interpreted as an
instruction by any component in the pipeline.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

# Strict base: unknown fields are a hard reject, no silent coercion of types.
Strict = ConfigDict(extra="forbid", strict=True, frozen=False)

CurrencyStr = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


def _decimal_from_wire(v: Any) -> Any:
    """JSON has no decimal type, so money arrives as a string. Floats are
    rejected outright: binary rounding has no business near an amount field."""
    if isinstance(v, Decimal):
        return v
    if isinstance(v, bool):
        raise ValueError("amount must be a decimal string")
    if isinstance(v, int):
        return Decimal(v)
    if isinstance(v, float):
        raise ValueError("send monetary amounts as decimal strings, not floats")
    if isinstance(v, str):
        try:
            return Decimal(v.strip())
        except InvalidOperation as exc:
            raise ValueError("amount is not a valid decimal") from exc
    raise ValueError("amount must be a decimal string")


Money = Annotated[
    Decimal,
    BeforeValidator(_decimal_from_wire),
    Field(gt=Decimal("0"), max_digits=12, decimal_places=2),
]


class SourceType(str, Enum):
    """Where the content around this transaction came from. Drives trust score."""

    OFFICIAL_API = "official_api"
    VERIFIED_CATALOG = "verified_catalog"
    SCRAPED_PAGE = "scraped_page"
    EMAIL = "email"
    USER_UPLOAD = "user_upload"
    UNKNOWN = "unknown"


class Decision(str, Enum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    BLOCK = "BLOCK"


class PaymentState(str, Enum):
    CREATED = "CREATED"
    AUTHORIZED = "AUTHORIZED"
    SUBMITTED = "SUBMITTED"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"
    EXPIRED = "EXPIRED"


class CartItem(BaseModel):
    model_config = Strict

    sku: Annotated[str, Field(min_length=1, max_length=128)]
    name: Annotated[str, Field(min_length=1, max_length=512)]
    quantity: Annotated[int, Field(gt=0, le=10_000)]
    unit_price: Money


class MerchantContent(BaseModel):
    """Untrusted text harvested from the merchant surface. Never an instruction."""

    model_config = Strict

    source_type: SourceType = SourceType.UNKNOWN
    source_url: Annotated[str, Field(max_length=2048)] = ""
    text: Annotated[str, Field(max_length=20_000)] = ""


class PaymentIntent(BaseModel):
    """The typed payment instruction. This is the only thing that can move money."""

    model_config = Strict

    idempotency_key: Annotated[str, Field(min_length=8, max_length=128)]
    agent_id: Annotated[str, Field(min_length=1, max_length=128)]
    user_id: Annotated[str, Field(min_length=1, max_length=128)]
    delegation_id: Annotated[str, Field(min_length=1, max_length=128)]

    merchant_id: Annotated[str, Field(min_length=1, max_length=128)]
    merchant_verified: bool = False

    amount: Money
    currency: CurrencyStr
    items: Annotated[list[CartItem], Field(min_length=1, max_length=200)]

    # --- untrusted free text (classified, never executed) ---
    purpose: Annotated[str, Field(max_length=2000)] = ""
    merchant_content: MerchantContent = Field(default_factory=MerchantContent)
    tool_arguments: dict[str, Any] = Field(default_factory=dict)

    # --- optional human-approval carry-over ---
    # Bounded, but wide enough for an RS256 JWT (~700 chars) — an approval
    # token is a signed record of what the human saw, not a short opaque id.
    approval_token: Annotated[str, Field(max_length=4096)] | None = None

    @field_validator("tool_arguments")
    @classmethod
    def _bounded_tool_arguments(cls, v: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(v, default=str)) > 8192:
            raise ValueError("tool_arguments exceeds 8KiB")
        return v

    def cart_hash(self) -> str:
        payload = [
            {"sku": i.sku, "quantity": i.quantity, "unit_price": str(i.unit_price)}
            for i in sorted(self.items, key=lambda i: i.sku)
        ]
        blob = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def payload_hash(self) -> str:
        """Hash of the money-moving fields; used to detect idempotency-key reuse
        with a *different* payload (replay) vs. an honest client retry."""
        blob = json.dumps(
            {
                "user_id": self.user_id,
                "agent_id": self.agent_id,
                "merchant_id": self.merchant_id,
                "amount": str(self.amount),
                "currency": self.currency,
                "cart_hash": self.cart_hash(),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()


class RiskSignals(BaseModel):
    """Evidence only. Contains no decision field, by design."""

    model_config = ConfigDict(extra="forbid")

    injection_confidence: float = 0.0
    injection_labels: list[str] = Field(default_factory=list)
    policy_violation_score: float = 0.0
    budget_anomaly_score: float = 0.0
    merchant_risk_score: float = 0.0
    velocity_risk_score: float = 0.0
    source_trust_score: float = 1.0
    classifier_degraded: bool = False


class RiskAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signals: RiskSignals
    weighted_score: float
    policy_version_context: str


class AuthorizationToken(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str
    payment_authorization_id: str
    merchant_id: str
    amount: Decimal
    currency: str
    cart_hash: str
    expires_at: datetime
    max_uses: Literal[1] = 1
    policy_version: str


class DecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_authorization_id: str
    decision: Decision
    reason_codes: list[str]
    state: PaymentState
    risk: RiskAssessment
    policy_version: str
    authorization: AuthorizationToken | None = None
    provider_reference: str | None = None
    audit_event_id: str | None = None
    audit_hash: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    replayed: bool = False
    message: str = ""
