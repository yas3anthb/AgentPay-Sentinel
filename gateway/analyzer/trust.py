"""Source trust scoring.

Where content came from changes how much weight a benign-looking reading of it
deserves. An official merchant API saying "ignore previous instructions" is
still an attack, but a scraped page is where we expect to find one.
"""
from __future__ import annotations

from gateway.schemas import SourceType

# 1.0 = fully trusted provenance, 0.0 = anonymous/unattributed.
TRUST: dict[SourceType, float] = {
    SourceType.OFFICIAL_API: 0.95,
    SourceType.VERIFIED_CATALOG: 0.8,
    SourceType.USER_UPLOAD: 0.5,
    SourceType.SCRAPED_PAGE: 0.25,
    SourceType.EMAIL: 0.15,
    SourceType.UNKNOWN: 0.1,
}


def trust_score(source: SourceType) -> float:
    return TRUST.get(source, 0.1)


def injection_prior(source: SourceType) -> float:
    """How much to amplify an injection signal found in content from this
    source. Low-trust provenance raises the amplifier, never lowers it below 1."""
    return 1.0 + (1.0 - trust_score(source)) * 0.25
