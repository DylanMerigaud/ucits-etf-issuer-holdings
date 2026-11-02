"""Issuer adapters and the order in which the client asks them."""

from __future__ import annotations

from .amundi import AmundiIssuer
from .base import Issuer
from .invesco import InvescoIssuer
from .ishares import ISharesIssuer
from .spdr import SpdrIssuer
from .vanguard import VanguardIssuer
from .xtrackers import XtrackersIssuer

ISSUERS: dict[str, Issuer] = {
    "ishares": ISharesIssuer(),
    "vanguard": VanguardIssuer(),
    "spdr": SpdrIssuer(),
    "xtrackers": XtrackersIssuer(),
    "amundi": AmundiIssuer(),
    "invesco": InvescoIssuer(),
}

# Issuers whose answer is an index (cached a day) come first, then the ones asked by ISIN.
ORDER = ("ishares", "vanguard", "spdr", "xtrackers", "amundi", "invesco")

__all__ = ["ISSUERS", "ORDER", "Issuer"]
