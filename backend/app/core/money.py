"""Money helpers. All amounts are ``Decimal`` UZS; never float."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0.00")
_CENTS = Decimal("0.01")
_SOM = Decimal("1")


def money(value: Decimal | int | str) -> Decimal:
    """Normalise to 2 decimal places (database precision)."""
    return Decimal(value).quantize(_CENTS, rounding=ROUND_HALF_UP)


def round_som(value: Decimal) -> Decimal:
    """Round to whole so'm (used for computed discounts), keeping 2-decimal form."""
    return value.quantize(_SOM, rounding=ROUND_HALF_UP).quantize(_CENTS)


def format_som(amount: Decimal) -> str:
    """``Decimal("1250000.00")`` → ``"1 250 000 so‘m"`` (no-break spaces)."""
    whole = int(amount.quantize(_SOM, rounding=ROUND_HALF_UP))
    return f"{whole:,}".replace(",", "\u00a0") + "\u00a0so‘m"
