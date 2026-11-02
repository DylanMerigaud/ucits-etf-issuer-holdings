"""Exceptions raised by the library. All of them subclass `HoldingsError`."""

from __future__ import annotations


class HoldingsError(Exception):
    """Base class of every error raised by this library."""


class InvalidISIN(HoldingsError):
    """The text is not a valid ISIN (shape or check digit)."""


class TransportError(HoldingsError):
    """A request failed before any answer came back (network, timeout, TLS)."""


class NotListed(HoldingsError):
    """The issuer does not list this ISIN."""

    def __init__(self, issuer: str, isin: str, reason: str = "not listed") -> None:
        super().__init__(f"{issuer}: {isin}: {reason}")
        self.issuer = issuer
        self.isin = isin
        self.reason = reason


class IssuerUnavailable(HoldingsError):
    """The issuer did not answer, or answered in a shape this library does not know."""

    def __init__(self, issuer: str, reason: str) -> None:
        super().__init__(f"{issuer}: {reason}")
        self.issuer = issuer
        self.reason = reason


class FundNotFound(HoldingsError):
    """No issuer answered with holdings; `reasons` says why each one did not."""

    def __init__(self, isin: str, reasons: dict[str, str]) -> None:
        detail = "; ".join(f"{name}: {why}" for name, why in reasons.items())
        super().__init__(f"{isin}: no issuer returned holdings ({detail})")
        self.isin = isin
        self.reasons = reasons
