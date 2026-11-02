"""Helpers shared by the issuer adapters."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Protocol, TypeVar
from urllib.parse import urlencode

from .. import countries
from ..errors import AccessDenied, IssuerUnavailable, NotListed, TransportError
from ..http import CachingTransport, Response, Transport, Validate
from ..models import Fund, Holding
from .asset_classes import normalize_asset_class

T = TypeVar("T")

INDEX_TTL = 24 * 3600.0
HOLDINGS_TTL = 6 * 3600.0

_LOOSE_ISIN = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")
_ISO_DATE = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2})(?:[T ].*)?", re.S)


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


def text(value: Any) -> str | None:
    """A stripped string when `value` is a non-empty string, else None (numbers included)."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def iso_date(value: Any) -> str | None:
    """`YYYY-MM-DD` from a date or a datetime string that starts with one; None otherwise."""
    if not isinstance(value, str):
        return None
    match = _ISO_DATE.fullmatch(value.strip())
    return match.group(1) if match else None


def as_dict(value: Any) -> dict[str, Any]:
    """`value` when it is a dict, else an empty dict (an optional object the issuer left out)."""
    return value if isinstance(value, dict) else {}


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
    issuer: str = "",
) -> Holding:
    """Build a Holding, filling `country` from the name or `country_name` from the code.

    `asset_class` is the issuer's own label; it is mapped to the vocabulary for `issuer`.
    """
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
        asset_class=normalize_asset_class(issuer, clean(asset_class)),
        asset_class_raw=clean(asset_class),
    )


def fetched_at(*responses: Response) -> str:
    """When the oldest of the answers used was fetched, as ISO 8601 UTC with a trailing Z."""
    oldest = min(response.stored_at for response in responses)
    return datetime.fromtimestamp(oldest, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    validate: Validate | None = None,
) -> Response:
    """Send a request; a network failure becomes IssuerUnavailable.

    `validate` is handed to a `CachingTransport` (other transports do not take it).
    """
    try:
        if validate is not None and isinstance(http, CachingTransport):
            return http.request(
                method, url, params=params, json=json, headers=headers, ttl=ttl, validate=validate
            )
        return http.request(method, url, params=params, json=json, headers=headers, ttl=ttl)
    except TransportError as exc:
        raise IssuerUnavailable(issuer, f"network error: {exc}") from exc


def fetch_parsed(
    issuer: str,
    http: Transport,
    method: str,
    url: str,
    parse: Callable[[Response], T],
    *,
    params: dict[str, str] | None = None,
    json: Any = None,
    headers: dict[str, str] | None = None,
    ttl: float | None = None,
) -> tuple[Response, T]:
    """Send a request and parse the answer with `parse`.

    A caching transport keeps a new answer only when `parse` accepts it (a `NotListed` counts as
    accepted: the answer is understood, the fund is not there). Otherwise it serves the previous
    copy, which is parsed in turn.
    """
    outcome: list[tuple[Response, Any]] = []

    def validate(response: Response) -> None:
        try:
            outcome.append((response, parse(response)))
        except NotListed as exc:
            outcome.append((response, exc))

    response = call(
        issuer,
        http,
        method,
        url,
        params=params,
        json=json,
        headers=headers,
        ttl=ttl,
        validate=validate,
    )
    if outcome and outcome[-1][0] is response:
        value = outcome[-1][1]
        if isinstance(value, NotListed):
            raise value
        return response, value
    return response, parse(response)


def require_ok(issuer: str, response: Response) -> None:
    """Raise unless the answer is a 200: AccessDenied for a 403, IssuerUnavailable otherwise."""
    if response.status == 403:
        raise AccessDenied(issuer, response.url)
    if response.status != 200:
        raise IssuerUnavailable(issuer, f"HTTP {response.status} from {response.url}")


def ok_json(issuer: str, response: Response) -> Any:
    """The parsed JSON of a 200 answer; a 403 is AccessDenied, anything else IssuerUnavailable."""
    require_ok(issuer, response)
    try:
        return response.json()
    except ValueError as exc:
        raise IssuerUnavailable(issuer, f"answer is not JSON ({response.url})") from exc


def require_holdings(issuer: str, holdings: list[Holding]) -> tuple[Holding, ...]:
    """The holdings as a tuple; an empty list means the answer shape is not understood."""
    if not holdings:
        raise IssuerUnavailable(issuer, "the answer holds no holdings")
    return tuple(holdings)
