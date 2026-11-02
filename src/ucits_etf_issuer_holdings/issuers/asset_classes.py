"""Map each issuer's own asset class label to the library's closed vocabulary."""

from __future__ import annotations

from typing import Any

# Labels compared lower-cased, per issuer.
_EXACT: dict[str, dict[str, str]] = {
    "ishares": {
        "equity": "equity",
        "fixed income": "fixed_income",
        "money market": "cash",
        "cash": "cash",
        "cash collateral and margins": "cash",
        "fx": "derivative",
        "futures": "derivative",
        "swaps": "derivative",
        "derivative": "derivative",
        "real estate": "real_estate",
        "commodity": "commodity",
    },
    "xtrackers": {
        "equities": "equity",
        "equity": "equity",
        "bonds": "fixed_income",
        "fixed income": "fixed_income",
        "cash": "cash",
        "currency": "cash",
        "futures": "derivative",
        "swaps": "derivative",
        "forwards": "derivative",
        "funds": "fund",
        "mutual fund": "fund",
    },
}

# Code prefixes compared upper-cased, per issuer, first match wins.
_PREFIX: dict[str, tuple[tuple[str, str], ...]] = {
    "vanguard": (
        ("EQ.REIT", "real_estate"),
        ("EQ.ETF", "fund"),
        ("EQ.", "equity"),
        ("MF.", "fund"),
        ("FI.", "fixed_income"),
        ("MM.", "cash"),
        ("CT.", "cash"),
        ("CRNY", "cash"),
        ("DE.", "derivative"),
    ),
    "amundi": (
        ("EQUITY", "equity"),
        ("BOND", "fixed_income"),
        ("FIXED_INCOME", "fixed_income"),
        ("CASH", "cash"),
        ("CURRENCY", "cash"),
        ("FUTURE", "derivative"),
        ("SWAP", "derivative"),
        ("FORWARD", "derivative"),
        ("OPTION", "derivative"),
        ("DERIVATIVE", "derivative"),
        ("FUND", "fund"),
        ("ETF", "fund"),
    ),
}


def normalize_asset_class(issuer: str, raw: Any) -> str | None:
    """The vocabulary value for an issuer's label: None when there is none, `other` if unknown."""
    if not isinstance(raw, str):
        return None
    label = raw.strip()
    if label in ("", "-"):
        return None
    exact = _EXACT.get(issuer, {}).get(label.lower())
    if exact is not None:
        return exact
    upper = label.upper()
    for prefix, value in _PREFIX.get(issuer, ()):
        if upper.startswith(prefix):
            return value
    return "other"
