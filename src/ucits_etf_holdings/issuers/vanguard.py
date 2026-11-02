"""Vanguard (Germany site): fund list page, GraphQL ISIN lookup and paged holdings."""

from __future__ import annotations

import json
import re
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
)

PRODUCTS_URL = "https://www.de.vanguard/professionell/anlageprodukte"
GRAPHQL_URL = "https://www.de.vanguard/gpx/graphql"
HEADERS = {"Content-Type": "application/json", "X-Consumer-ID": "de7"}
MAX_PAGES = 20

FUNDS_QUERY = (
    "query FundsQuery($portIds: [String!]!) { funds(portIds: $portIds) { portId profile "
    '{ portId fundFullName fundCurrency identifiers(altIds: ["ISIN"]) '
    "{ altId altIdCode altIdValue } } } }"
)

HOLDINGS_QUERY = """query FundsHoldingsQuery($portIds: [String!], $securityTypes: [String!], $lastItemKey: String) {
    funds(portIds: $portIds) {
      profile {
        fundFullName
        fundCurrency
        primarySectorEquityClassification
      }
    }
    borHoldings(portIds: $portIds) {
      holdings(limit: 1500, securityTypes: $securityTypes, lastItemKey: $lastItemKey) {
        items {
          issuerName
          securityLongDescription
          gicsSectorDescription
          icbSectorDescription
          icbIndustryDescription
          marketValuePercentage
          sedol1
          quantity
          ticker
          securityType
          finalMaturity
          effectiveDate
          marketValueBaseCurrency
          bloombergIsoCountry
          couponRate
        }
        totalHoldings
        lastItemKey
      }
    }
  }"""  # noqa: E501

_STATE = re.compile(r'<script id="serverApp-state"[^>]*>(.*?)</script>', re.S)


class VanguardIssuer:
    """Adapter for Vanguard UCITS ETFs and funds listed on the German site."""

    name = "vanguard"

    def _port_ids(self, page: str) -> list[str]:
        match = _STATE.search(page)
        if match is None:
            raise IssuerUnavailable(self.name, "serverApp-state script not found")
        try:
            state = json.loads(match.group(1))
            ids = state["_angular_initial_state"][":items"]["root"][":items"]["site-config"][
                "portIds"
            ]
        except (ValueError, KeyError, TypeError) as exc:
            raise IssuerUnavailable(self.name, "portIds missing in the page state") from exc
        return [part.strip() for part in str(ids).split(",") if part.strip()]

    def _graphql(
        self, http: Transport, operation: str, query: str, variables: dict[str, Any], ttl: float
    ) -> tuple[dict[str, Any], bool]:
        body = {"operationName": operation, "variables": variables, "query": query}
        answer = call(self.name, http, "POST", GRAPHQL_URL, json=body, headers=HEADERS, ttl=ttl)
        data = ok_json(self.name, answer)
        if (
            not isinstance(data, dict)
            or data.get("errors")
            or not isinstance(data.get("data"), dict)
        ):
            raise IssuerUnavailable(self.name, f"GraphQL {operation} answered with errors")
        return data["data"], answer.stale

    def fetch(self, isin: str, http: Transport) -> Fund:
        """Find the portfolio id of the ISIN, then page through its holdings."""
        page = call(self.name, http, "GET", PRODUCTS_URL, ttl=INDEX_TTL)
        if page.status != 200:
            raise IssuerUnavailable(self.name, f"HTTP {page.status} from {page.url}")
        port_ids = self._port_ids(page.text)
        funds, stale = self._graphql(
            http, "FundsQuery", FUNDS_QUERY, {"portIds": port_ids}, INDEX_TTL
        )
        stale = stale or page.stale
        port_id = None
        for fund in funds.get("funds") or []:
            identifiers = (fund.get("profile") or {}).get("identifiers") or []
            if any(i.get("altIdValue") == isin for i in identifiers):
                port_id = str(fund["portId"])
                break
        if port_id is None:
            raise NotListed(self.name, isin, "not in the Vanguard fund list")

        holdings: list[Holding] = []
        profile: dict[str, Any] = {}
        dates: list[str] = []
        key: Any = None
        for _ in range(MAX_PAGES):
            data, page_stale = self._graphql(
                http,
                "FundsHoldingsQuery",
                HOLDINGS_QUERY,
                {"portIds": [port_id], "lastItemKey": key},
                HOLDINGS_TTL,
            )
            stale = stale or page_stale
            try:
                profile = profile or data["funds"][0]["profile"]
                block = data["borHoldings"][0]["holdings"]
                items = block["items"]
                key = block.get("lastItemKey")
            except (KeyError, IndexError, TypeError) as exc:
                raise IssuerUnavailable(self.name, "holdings path missing in the answer") from exc
            for item in items:
                weight = number(item.get("marketValuePercentage"))
                name = item.get("issuerName") or item.get("securityLongDescription")
                if weight is None or not name:
                    continue
                if item.get("effectiveDate"):
                    dates.append(str(item["effectiveDate"]))
                holdings.append(
                    make_holding(
                        str(name),
                        weight,
                        ticker=item.get("ticker"),
                        country=item.get("bloombergIsoCountry"),
                        sector=item.get("gicsSectorDescription")
                        or item.get("icbSectorDescription"),
                        asset_class=item.get("securityType"),
                    )
                )
            if not key:
                break
        else:
            raise IssuerUnavailable(self.name, f"more than {MAX_PAGES} pages of holdings")
        return Fund(
            isin=isin,
            issuer=self.name,
            fund_name=profile.get("fundFullName"),
            as_of=max(dates) if dates else None,
            currency=profile.get("fundCurrency"),
            source_url=GRAPHQL_URL,
            fetched_at=now_utc(),
            stale=stale,
            holdings=require_holdings(self.name, holdings),
        )
