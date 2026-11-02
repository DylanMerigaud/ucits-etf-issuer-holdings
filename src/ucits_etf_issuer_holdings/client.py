"""`HoldingsClient`: validate the ISIN, ask the issuers in order, return the first holdings."""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
from pathlib import Path
from types import TracebackType

from .errors import AccessDenied, FundNotFound, HoldingsError, IssuerUnavailable, NotListed
from .http import DEFAULT_CACHE_DIR, CachingTransport, HttpxTransport, Transport
from .isin import normalize
from .issuers import ISSUERS, ORDER
from .models import Fund


class _Default(Enum):
    """Marks a `cache_dir` the caller did not pass."""

    CACHE_DIR = "default"


class HoldingsClient:
    """Fetches the holdings an issuer publishes for an ISIN.

    With no `transport` the client uses httpx and an on-disk cache in `DEFAULT_CACHE_DIR`;
    `proxy` then sends every request through that proxy URL (see `HttpxTransport`).
    A transport you pass is used as it is, without a cache, unless you also pass a `cache_dir`
    (any directory, the default one included). `cache_dir=None` never caches.

    Use it as a context manager, or call `close()`, to release the connections it opened.
    """

    def __init__(
        self,
        transport: Transport | None = None,
        cache_dir: str | Path | _Default | None = _Default.CACHE_DIR,
        issuers: Iterable[str] | None = None,
        timeout: float = 30.0,
        proxy: str | None = None,
    ) -> None:
        if transport is not None and proxy is not None:
            raise ValueError("proxy= applies to the default transport; pass one or the other")
        names = tuple(issuers) if issuers is not None else ORDER
        unknown = [name for name in names if name not in ISSUERS]
        if unknown:
            raise ValueError(f"unknown issuer(s): {', '.join(unknown)}")
        self._names = names
        self._own: HttpxTransport | None = None
        base: Transport
        if transport is None:
            self._own = base = HttpxTransport(timeout=timeout, proxy=proxy)
        else:
            base = transport
        if cache_dir is _Default.CACHE_DIR:
            cache_dir = DEFAULT_CACHE_DIR if transport is None else None
        if cache_dir is not None:
            self._http: Transport = CachingTransport(base, cache_dir)
        else:
            self._http = base

    def close(self) -> None:
        """Close the network client this object made (a transport you passed stays open)."""
        if self._own is not None:
            self._own.close()

    def __enter__(self) -> HoldingsClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def get(self, isin: str, issuer: str | None = None) -> Fund:
        """Return the fund for `isin`, asking only `issuer` when given.

        Raises `InvalidISIN`, `ValueError` for an unknown issuer name, or `FundNotFound` when no
        issuer answered with holdings (its `blocked` names the issuers whose site refused this
        network address).
        """
        code = normalize(isin)
        if issuer is not None:
            if issuer not in ISSUERS:
                raise ValueError(f"unknown issuer: {issuer!r}")
            names: tuple[str, ...] = (issuer,)
        else:
            names = self._names
        reasons: dict[str, str] = {}
        blocked: list[str] = []
        for name in names:
            try:
                fund = ISSUERS[name].fetch(code, self._http)
            except AccessDenied as exc:
                reasons[name] = exc.reason
                blocked.append(name)
                continue
            except (NotListed, IssuerUnavailable) as exc:
                reasons[name] = exc.reason
                continue
            except HoldingsError:
                raise
            except Exception as exc:  # one malformed answer must not stop the lookup
                reasons[name] = f"unexpected answer: {type(exc).__name__}: {exc}"
                continue
            return fund
        raise FundNotFound(code, reasons, tuple(blocked))


def get_holdings(
    isin: str,
    issuer: str | None = None,
    *,
    transport: Transport | None = None,
    cache_dir: str | Path | _Default | None = _Default.CACHE_DIR,
    timeout: float = 30.0,
    proxy: str | None = None,
) -> Fund:
    """One-call form of `HoldingsClient(...).get(isin, issuer)`; the client is closed after."""
    with HoldingsClient(
        transport=transport, cache_dir=cache_dir, timeout=timeout, proxy=proxy
    ) as client:
        return client.get(isin, issuer)
