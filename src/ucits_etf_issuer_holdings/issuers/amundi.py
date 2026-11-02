"""Amundi ETF (Germany site): one product API call per ISIN."""

from __future__ import annotations

from typing import Any

from ..errors import IssuerUnavailable, NotListed
from ..http import Response, Transport
from ..models import Fund, Holding
from .base import (
    HOLDINGS_TTL,
    as_dict,
    fetch_parsed,
    fetched_at,
    iso_date,
    make_holding,
    number,
    ok_json,
    require_holdings,
    text,
)

URL = "https://www.amundietf.de/mapi/ProductAPI/getProductsData"
FIELDS = ["date", "type", "isin", "name", "weight", "currency", "sector", "countryOfRisk"]


def _parse(response: Response, isin: str) -> tuple[dict[str, Any], tuple[Holding, ...], str | None]:
    """The product, its holdings and the as-of date; an empty product list is NotListed."""
    data = ok_json("amundi", response)
    products = data.get("products") if isinstance(data, dict) else None
    if not isinstance(products, list):
        raise IssuerUnavailable("amundi", "products missing in the answer")
    if not products:
        raise NotListed("amundi", isin, "the product list is empty")
    product = products[0]
    rows = (
        as_dict(product.get("composition")).get("compositionData")
        if isinstance(product, dict)
        else None
    )
    if not isinstance(product, dict) or not isinstance(rows, list):
        raise IssuerUnavailable("amundi", "composition missing in the answer")
    holdings: list[Holding] = []
    dates: list[str] = []
    for row in rows:
        item = as_dict(row.get("compositionCharacteristics")) if isinstance(row, dict) else {}
        weight = number(item.get("weight"))
        if weight is None or not item.get("name"):
            continue
        date = iso_date(item.get("date"))
        if date is not None:
            dates.append(date)
        holdings.append(
            make_holding(
                str(item["name"]),
                round(weight * 100, 10),
                isin=item.get("isin"),
                country_name=item.get("countryOfRisk"),
                sector=item.get("sector"),
                currency=item.get("currency"),
                asset_class=item.get("type"),
            )
        )
    return product, require_holdings("amundi", holdings), max(dates) if dates else None


class AmundiIssuer:
    """Adapter for Amundi UCITS ETFs. Swap based funds publish their substitute basket."""

    name = "amundi"

    def fetch(self, isin: str, http: Transport) -> Fund:
        """Ask the product API for the ISIN; an empty product list means not listed."""
        body = {
            "context": {"countryCode": "DEU", "languageCode": "de", "userProfileName": "RETAIL"},
            "productIds": [isin],
            "productType": "PRODUCT",
            "characteristics": ["SHARE_MARKETING_NAME"],
            "composition": {"compositionFields": FIELDS},
        }
        answer, (product, holdings, as_of) = fetch_parsed(
            self.name,
            http,
            "POST",
            URL,
            lambda response: _parse(response, isin),
            json=body,
            ttl=HOLDINGS_TTL,
        )
        return Fund(
            isin=isin,
            issuer=self.name,
            fund_name=text(as_dict(product.get("characteristics")).get("SHARE_MARKETING_NAME")),
            as_of=as_of,
            currency=text(as_dict(product.get("currencies")).get("BASE_CURRENCY")),
            source_url=URL,
            fetched_at=fetched_at(answer),
            stale=answer.stale,
            holdings=holdings,
        )
