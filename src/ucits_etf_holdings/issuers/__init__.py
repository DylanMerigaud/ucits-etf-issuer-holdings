"""Issuer adapters and the order in which the client asks them."""

from __future__ import annotations

from .base import Issuer
from .ishares import ISharesIssuer
from .spdr import SpdrIssuer
from .vanguard import VanguardIssuer

ISSUERS: dict[str, Issuer] = {
    "ishares": ISharesIssuer(),
    "vanguard": VanguardIssuer(),
    "spdr": SpdrIssuer(),
}

ORDER = ("ishares", "vanguard", "spdr", "xtrackers", "amundi", "invesco")

__all__ = ["ISSUERS", "ORDER", "Issuer"]
