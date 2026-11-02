"""Helpers shared by the issuer adapters."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlencode

from .. import countries
from ..errors import IssuerUnavailable, TransportError
from ..http import Response, Transport
from ..models import Fund, Holding

INDEX_TTL = 24 * 3600.0
HOLDINGS_TTL = 6 * 3600.0

_LOOSE_ISIN = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")


class Issuer(Protocol):
    """An issuer adapter: a `name` and a `fetch` returning the fund's holdings."""

    name: str

    def fetch(self, isin: str, http: Transport) -> Fund:
        """Return the fund, or raise `NotListed` or `IssuerUnavailable`."""
        ...


def clean(value: Any) -> str | None:
    """A stripped string, or None for None, blank and the dash placeholders issuers use."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text in ("", "-") else text


def clean_isin(value: Any) -> str | None:
    """An ISIN-shaped string or None (cash lines carry labels such as `_CURRENCYEUR`)."""
    text = clean(value)
    if text is None:
        return None
    text = text.upper()
    return text if _LOOSE_ISIN.fullmatch(text) else None


def number(value: Any) -> float | None:
    """A float for int, float and numeric strings; None otherwise (booleans included)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def make_holding(
    name: str,
    weight: float,
    *,
    isin: Any = None,
    ticker: Any = None,
    country: Any = None,
    country_name: Any = None,
    sector: Any = None,
    currency: Any = None,
    asset_class: Any = None,
) -> Holding:
    """Build a Holding, filling `country` from the name or `country_name` from the code."""
    code = countries.to_iso2(clean(country)) if country is not None else None
    label = clean(country_name)
    if code is None and label is not None:
        code = countries.to_iso2(label)
    if label is None and code is not None:
        label = countries.name_of(code)
    return Holding(
        name=name,
        weight=weight,
        isin=clean_isin(isin),
        ticker=clean(ticker),
        country=code,
        country_name=label,
        sector=clean(sector),
        currency=clean(currency),
        asset_class=clean(asset_class),
    )


def now_utc() -> str:
    """The current time as ISO 8601 UTC with a trailing Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def with_params(url: str, params: dict[str, str] | None) -> str:
    """The url with its query string, as it is requested."""
    return f"{url}?{urlencode(params)}" if params else url


def call(
    issuer: str,
    http: Transport,
    method: str,
    url: str,
    *,
    params: dict[str, str] | None = None,
    json: Any = None,
    headers: dict[str, str] | None = None,
    ttl: float | None = None,
) -> Response:
    """Send a request; a network failure becomes IssuerUnavailable."""
    try:
        return http.request(method, url, params=params, json=json, headers=headers, ttl=ttl)
    except TransportError as exc:
        raise IssuerUnavailable(issuer, f"network error: {exc}") from exc


def ok_json(issuer: str, response: Response) -> Any:
    """The parsed JSON of a 200 answer; anything else is IssuerUnavailable."""
    if response.status != 200:
        raise IssuerUnavailable(issuer, f"HTTP {response.status} from {response.url}")
    try:
        return response.json()
    except ValueError as exc:
        raise IssuerUnavailable(issuer, f"answer is not JSON ({response.url})") from exc


def require_holdings(issuer: str, holdings: list[Holding]) -> tuple[Holding, ...]:
    """The holdings as a tuple; an empty list means the answer shape is not understood."""
    if not holdings:
        raise IssuerUnavailable(issuer, "the answer holds no holdings")
    return tuple(holdings)
