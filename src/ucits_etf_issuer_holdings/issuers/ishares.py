"""iShares (BlackRock): product screener index plus the column oriented holdings component."""

from __future__ import annotations

from typing import Any

from ..errors import IssuerUnavailable, NotListed
from ..http import Transport
from ..models import Fund, Holding
from .base import (
    HOLDINGS_TTL,
    INDEX_TTL,
    call,
    make_holding,
    now_utc,
    number,
    ok_json,
    require_holdings,
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


class ISharesIssuer:
    """Adapter for iShares UCITS ETFs."""

    name = "ishares"

    def fetch(self, isin: str, http: Transport) -> Fund:
        """Look the ISIN up in the screener index, then read the holdings component."""
        index_answer = call(self.name, http, "GET", INDEX_URL, params=INDEX_PARAMS, ttl=INDEX_TTL)
        index = ok_json(self.name, index_answer)
        if not isinstance(index, dict):
            raise IssuerUnavailable(self.name, "the product index is not an object")
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
        portfolio_id = str(_raw(entry.get("portfolioId")))
        params = {
            "appSubType": "ISHARES",
            "appType": "PRODUCT_PAGE",
            "component": "holdings",
            "locale": "en_GB",
            "portfolioId": portfolio_id,
            "targetSite": "ishares-uk",
            "userType": "individual",
            "excludeContent": "true",
            "includeConfig": "false",
        }
        answer = call(self.name, http, "GET", HOLDINGS_URL, params=params, ttl=HOLDINGS_TTL)
        data = ok_json(self.name, answer)
        try:
            points = data["componentsByNameMap"]["holdings"]["containersByNameMap"]["all"][
                "dataPointsByNameMap"
            ]
            names = points["issueName"]["value"]
            weights = points["holdingPercent"]["value"]
        except (KeyError, TypeError) as exc:
            raise IssuerUnavailable(self.name, "holdings path missing in the answer") from exc

        def column(key: str) -> list[Any]:
            values = (points.get(key) or {}).get("value")
            return values if isinstance(values, list) else [None] * len(names)

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
                )
            )
        return Fund(
            isin=isin,
            issuer=self.name,
            fund_name=_raw(entry.get("fundName")),
            as_of=_as_of((points.get("asOfDate") or {}).get("value")),
            currency=_raw(entry.get("seriesBaseCurrencyCode")),
            source_url=with_params(HOLDINGS_URL, params),
            fetched_at=now_utc(),
            stale=index_answer.stale or answer.stale,
            holdings=require_holdings(self.name, holdings),
        )
