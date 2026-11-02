"""Issuer adapters and the order in which the client asks them."""

from __future__ import annotations

from .base import Issuer
from .ishares import ISharesIssuer
from .vanguard import VanguardIssuer

ISSUERS: dict[str, Issuer] = {"ishares": ISharesIssuer(), "vanguard": VanguardIssuer()}

ORDER = ("ishares", "vanguard", "spdr", "xtrackers", "amundi", "invesco")

__all__ = ["ISSUERS", "ORDER", "Issuer"]
