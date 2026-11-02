"""`HoldingsClient`: validate the ISIN, ask the issuers in order, return the first holdings."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .errors import FundNotFound, HoldingsError, IssuerUnavailable, NotListed
from .http import DEFAULT_CACHE_DIR, CachingTransport, HttpxTransport, Transport
from .isin import normalize
from .issuers import ISSUERS, ORDER
from .models import Fund


class HoldingsClient:
    """Fetches the holdings an issuer publishes for an ISIN.

    With no `transport` the client uses httpx and, when `cache_dir` is set, an on-disk cache.
    A transport you pass is used as it is, unless you also pass your own `cache_dir`.
    """

    def __init__(
        self,
        transport: Transport | None = None,
        cache_dir: str | Path | None = DEFAULT_CACHE_DIR,
        issuers: Iterable[str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        names = tuple(issuers) if issuers is not None else ORDER
        unknown = [name for name in names if name not in ISSUERS]
        if unknown:
            raise ValueError(f"unknown issuer(s): {', '.join(unknown)}")
        self._names = names
        base = transport if transport is not None else HttpxTransport(timeout=timeout)
        if cache_dir is not None and (transport is None or cache_dir is not DEFAULT_CACHE_DIR):
            self._http: Transport = CachingTransport(base, cache_dir)
        else:
            self._http = base

    def get(self, isin: str, issuer: str | None = None) -> Fund:
        """Return the fund for `isin`, asking only `issuer` when given.

        Raises `InvalidISIN`, `ValueError` for an unknown issuer name, or `FundNotFound` when no
        issuer answered with holdings.
        """
        code = normalize(isin)
        if issuer is not None:
            if issuer not in ISSUERS:
                raise ValueError(f"unknown issuer: {issuer!r}")
            names: tuple[str, ...] = (issuer,)
        else:
            names = self._names
        reasons: dict[str, str] = {}
        for name in names:
            try:
                fund = ISSUERS[name].fetch(code, self._http)
            except (NotListed, IssuerUnavailable) as exc:
                reasons[name] = exc.reason
                continue
            except HoldingsError:
                raise
            except Exception as exc:  # one malformed answer must not stop the lookup
                reasons[name] = f"unexpected answer: {type(exc).__name__}: {exc}"
                continue
            return fund
        raise FundNotFound(code, reasons)


def get_holdings(
    isin: str,
    issuer: str | None = None,
    *,
    transport: Transport | None = None,
    cache_dir: str | Path | None = DEFAULT_CACHE_DIR,
    timeout: float = 30.0,
) -> Fund:
    """One-call form of `HoldingsClient(...).get(isin, issuer)`."""
    client = HoldingsClient(transport=transport, cache_dir=cache_dir, timeout=timeout)
    return client.get(isin, issuer)
