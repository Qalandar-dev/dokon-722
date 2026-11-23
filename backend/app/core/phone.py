"""Uzbek phone number normalisation to E.164 (+998XXXXXXXXX)."""

from __future__ import annotations

import re

from app.core.exceptions import BusinessRuleError

_DIGITS = re.compile(r"\D+")


def normalize_uz_phone(raw: str) -> str:
    """Accepts "+998 90 123-45-67", "998901234567", "90 123 45 67", "8 90 1234567"."""
    digits = _DIGITS.sub("", raw or "")
    if len(digits) == 9:
        digits = "998" + digits
    elif len(digits) == 10 and digits.startswith("8"):
        digits = "998" + digits[1:]
    if len(digits) != 12 or not digits.startswith("998"):
        raise BusinessRuleError(
            "Telefon raqami noto‘g‘ri. Namuna: +998 90 123 45 67.", code="invalid_phone"
        )
    return "+" + digits
