"""Money as integer minor units.

Amounts travel the wire as decimal strings (``gateway.schemas.Money`` rejects
floats outright) and are stored as ``Numeric(12, 2)``. The one place they used
to lose exactness was the hop into OPA: JSON has no decimal type, so a
``Decimal`` became a float64 and every ``>`` / ``==`` in Rego was a binary
comparison.

`to_minor_units` is the single conversion used at that boundary. Everything OPA
sees for an amount, a limit, or an approval binding is an integer number of
minor units (paise / cents), so the policy compares integers and an exact
equality in ``approvals.rego`` is genuinely exact.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# Two decimal places is baked into the wire type (`Money` has
# `decimal_places=2`) and the DB columns (`Numeric(12, 2)`). If a currency with
# a different exponent ever matters, this is the one place that changes.
MINOR_UNIT_SCALE = Decimal(100)


def to_minor_units(value: Decimal | int | float | str) -> int:
    """Convert a major-unit amount to an integer count of minor units.

    Accepts what the pipeline actually carries: ``Decimal`` (canonical
    transaction, policy context), or a string (JWT ``bound_amount`` claim).
    Floats are tolerated defensively but never originate here — the wire layer
    rejects them.
    """
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return int((value * MINOR_UNIT_SCALE).to_integral_value(rounding=ROUND_HALF_UP))
