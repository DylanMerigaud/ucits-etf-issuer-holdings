"""Amundi ETF (Germany site): one product API call per ISIN."""

from __future__ import annotations

from typing import Any

from ..errors import IssuerUnavailable, NotListed
from ..http import Transport
from ..models import Fund, Holding
from .base import HOLDINGS_TTL, call, make_holding, now_utc, number, ok_json, require_holdings

URL = "https://www.amundietf.de/mapi/ProductAPI/getProductsData"
FIELDS = ["date", "type", "isin", "name", "weight", "currency", "sector", "countryOfRisk"]


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
        answer = call(self.name, http, "POST", URL, json=body, ttl=HOLDINGS_TTL)
        data = ok_json(self.name, answer)
        products = data.get("products") if isinstance(data, dict) else None
        if not isinstance(products, list):
            raise IssuerUnavailable(self.name, "products missing in the answer")
        if not products:
            raise NotListed(self.name, isin, "the product list is empty")
        product: dict[str, Any] = products[0]
        try:
            rows = product["composition"]["compositionData"]
        except (KeyError, TypeError) as exc:
            raise IssuerUnavailable(self.name, "composition missing in the answer") from exc
        holdings: list[Holding] = []
        dates: list[str] = []
        for row in rows:
            item = row.get("compositionCharacteristics") or {}
            weight = number(item.get("weight"))
            if weight is None or not item.get("name"):
                continue
            if item.get("date"):
                dates.append(str(item["date"]))
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
        return Fund(
            isin=isin,
            issuer=self.name,
            fund_name=(product.get("characteristics") or {}).get("SHARE_MARKETING_NAME"),
            as_of=max(dates) if dates else None,
            currency=(product.get("currencies") or {}).get("BASE_CURRENCY"),
            source_url=URL,
            fetched_at=now_utc(),
            stale=answer.stale,
            holdings=require_holdings(self.name, holdings),
        )
