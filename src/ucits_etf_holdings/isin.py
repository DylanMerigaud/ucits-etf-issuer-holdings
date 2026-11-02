"""ISIN validation."""

from __future__ import annotations

import re

from .errors import InvalidISIN

_SHAPE = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")


def _luhn_ok(isin: str) -> bool:
    """Check the Luhn digit on the string with letters expanded to two digits (A=10)."""
    digits = "".join(str(int(ch, 36)) for ch in isin)
    total = 0
    for index, ch in enumerate(reversed(digits)):
        value = int(ch)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def normalize(isin: str) -> str:
    """Return the ISIN stripped and upper-cased, or raise `InvalidISIN`."""
    if not isinstance(isin, str):
        raise InvalidISIN(f"ISIN must be a string, got {type(isin).__name__}")
    text = isin.strip().upper()
    if not _SHAPE.fullmatch(text):
        raise InvalidISIN(f"not an ISIN: {isin!r}")
    if not _luhn_ok(text):
        raise InvalidISIN(f"bad check digit: {isin!r}")
    return text
