"""Country names and ISO 3166-1 alpha-2 codes."""

from __future__ import annotations

from ._country_data import ISO2_TO_NAME, NAME_TO_ISO2


def to_iso2(text: str | None) -> str | None:
    """Return the alpha-2 code for a country name or code, or None when unknown."""
    if not text:
        return None
    cleaned = text.strip()
    if len(cleaned) == 2 and cleaned.isalpha():
        code = cleaned.upper()
        return code if code in ISO2_TO_NAME else None
    return NAME_TO_ISO2.get(cleaned.lower())


def name_of(code: str | None) -> str | None:
    """Return the English country name for an alpha-2 code, or None when unknown."""
    if not code:
        return None
    return ISO2_TO_NAME.get(code.strip().upper())
