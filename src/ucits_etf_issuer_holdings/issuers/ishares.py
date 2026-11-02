"""iShares (BlackRock): product screener index plus the column oriented holdings component."""

from __future__ import annotations

from typing import Any

from ..errors import IssuerUnavailable, NotListed
from ..http import Response, Transport
from ..models import Fund, Holding
from .base import (
    HOLDINGS_TTL,
    INDEX_TTL,
    as_dict,
    fetch_parsed,
    fetched_at,
    make_holding,
    number,
    ok_json,
    require_holdings,
    text,
    with_params,
)

INDEX_URL = (
    "https://www.ishares.com/varnish-api/blk-product-screener-server/api/v1/product-screener/"
    "product-data"
)
INDEX_PARAMS = {
    "country": "de",
    "language": "de",
    "siteName": "de-ishares-v2",
    "userType": "individual",
}
HOLDINGS_URL = (
    "https://www.ishares.com/varnish-api/uk-retail01-product-data/product-data/api/v2/"
    "get-product-data"
)


def _raw(value: Any) -> Any:
    """Unwrap the `{"r": raw, "d": display}` form some values come in."""
    if isinstance(value, dict) and "r" in value:
        return value["r"]
    return value


def _as_of(value: Any) -> str | None:
    """`20261030` as `2026-10-30`."""
    text = str(_raw(value)) if value is not None else ""
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return None


def _parse_index(response: Response) -> dict[str, Any]:
    index = ok_json("ishares", response)
    if not isinstance(index, dict):
        raise IssuerUnavailable("ishares", "the product index is not an object")
    return index


def _parse_holdings(response: Response) -> tuple[tuple[Holding, ...], str | None]:
    """The holdings and the as-of date of a holdings component answer."""
    node: Any = ok_json("ishares", response)
    for key in (
        "componentsByNameMap",
        "holdings",
        "containersByNameMap",
        "all",
        "dataPointsByNameMap",
    ):
        node = node.get(key) if isinstance(node, dict) else None
    points: Any = node
    names = as_dict(points.get("issueName")).get("value") if isinstance(points, dict) else None
    weights = (
        as_dict(points.get("holdingPercent")).get("value") if isinstance(points, dict) else None
    )
    if not isinstance(points, dict) or not isinstance(names, list) or not isinstance(weights, list):
        raise IssuerUnavailable("ishares", "holdings path missing in the answer")

    def column(key: str) -> list[Any]:
        values = as_dict(points.get(key)).get("value")
        values = values if isinstance(values, list) else []
        return values + [None] * (len(names) - len(values))

    columns = {
        key: column(key)
        for key in (
            "isin",
            "ticker",
            "countryOfRisk",
            "sectorName",
            "marketCurrencyCode",
            "assetClass",
        )
    }
    holdings: list[Holding] = []
    for position, name in enumerate(names):
        weight = number(weights[position]) if position < len(weights) else None
        if weight is None or name is None:
            continue
        holdings.append(
            make_holding(
                str(name),
                weight,
                isin=columns["isin"][position],
                ticker=columns["ticker"][position],
                country_name=columns["countryOfRisk"][position],
                sector=columns["sectorName"][position],
                currency=columns["marketCurrencyCode"][position],
                asset_class=columns["assetClass"][position],
                issuer="ishares",
            )
        )
    as_of = _as_of(as_dict(points.get("asOfDate")).get("value"))
    return require_holdings("ishares", holdings), as_of


class ISharesIssuer:
    """Adapter for iShares UCITS ETFs."""

    name = "ishares"

    def fetch(self, isin: str, http: Transport) -> Fund:
        """Look the ISIN up in the screener index, then read the holdings component."""
        index_answer, index = fetch_parsed(
            self.name, http, "GET", INDEX_URL, _parse_index, params=INDEX_PARAMS, ttl=INDEX_TTL
        )
        entry = next(
            (
                value
                for value in index.values()
                if isinstance(value, dict) and _raw(value.get("isin")) == isin
            ),
            None,
        )
        if entry is None:
            raise NotListed(self.name, isin, "not in the iShares product index")
        portfolio_id = _raw(entry.get("portfolioId"))
        if isinstance(portfolio_id, bool) or not isinstance(portfolio_id, (str, int)):
            raise IssuerUnavailable(self.name, "portfolioId missing for the fund")
        if not str(portfolio_id).strip():
            raise IssuerUnavailable(self.name, "portfolioId missing for the fund")
        params = {
            "appSubType": "ISHARES",
            "appType": "PRODUCT_PAGE",
            "component": "holdings",
            "locale": "en_GB",
            "portfolioId": str(portfolio_id),
            "targetSite": "ishares-uk",
            "userType": "individual",
            "excludeContent": "true",
            "includeConfig": "false",
        }
        answer, (holdings, as_of) = fetch_parsed(
            self.name, http, "GET", HOLDINGS_URL, _parse_holdings, params=params, ttl=HOLDINGS_TTL
        )
        return Fund(
            isin=isin,
            issuer=self.name,
            fund_name=text(_raw(entry.get("fundName"))),
            as_of=as_of,
            currency=text(_raw(entry.get("seriesBaseCurrencyCode"))),
            source_url=with_params(HOLDINGS_URL, params),
            fetched_at=fetched_at(index_answer, answer),
            stale=index_answer.stale or answer.stale,
            holdings=holdings,
        )
