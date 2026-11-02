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


class AccessDenied(IssuerUnavailable):
    """The issuer's site refused this network address (HTTP 403 before any data).

    iShares (BlackRock) serves its site through Akamai, which refuses most cloud and datacenter
    address ranges whatever the request looks like, so the same call that works from a home
    connection fails from a server or a CI runner. `url` is the address that refused.
    """

    def __init__(self, issuer: str, url: str) -> None:
        super().__init__(
            issuer,
            f"HTTP 403 from {url}: the site refused this network address (its CDN blocks most "
            "cloud and datacenter IP ranges, whatever the request headers); run from a "
            "residential connection or send the requests through a proxy on one (README, "
            "'Blocked by an issuer')",
        )
        self.url = url


class FundNotFound(HoldingsError):
    """No issuer answered with holdings; `reasons` says why each one did not.

    `blocked` names the issuers that refused this network address (`AccessDenied`): the fund may
    be theirs, the library could not ask.
    """

    def __init__(self, isin: str, reasons: dict[str, str], blocked: tuple[str, ...] = ()) -> None:
        detail = "; ".join(f"{name}: {why}" for name, why in reasons.items())
        lead = (
            f"{isin}: no issuer returned holdings, and {', '.join(blocked)} refused this network "
            "address, so the fund may be theirs"
            if blocked
            else f"{isin}: no issuer returned holdings"
        )
        super().__init__(f"{lead} ({detail})")
        self.isin = isin
        self.reasons = reasons
        self.blocked = blocked
