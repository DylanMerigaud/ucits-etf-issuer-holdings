"""Vanguard (Germany site): fund list page, GraphQL ISIN lookup and paged holdings."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, TypeVar

from ..errors import IssuerUnavailable, NotListed
from ..http import Response, Transport
from ..models import Fund, Holding
from .base import (
    HOLDINGS_TTL,
    INDEX_TTL,
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

T = TypeVar("T")

_STATE = re.compile(r'<script id="serverApp-state"[^>]*>(.*?)</script>', re.S)


def _parse_page(response: Response) -> list[str]:
    """The portfolio ids listed in the fund list page's state script."""
    if response.status != 200:
        raise IssuerUnavailable("vanguard", f"HTTP {response.status} from {response.url}")
    match = _STATE.search(response.text)
    if match is None:
        raise IssuerUnavailable("vanguard", "serverApp-state script not found")
    try:
        node: Any = json.loads(match.group(1))
    except ValueError as exc:
        raise IssuerUnavailable("vanguard", "portIds missing in the page state") from exc
    for key in ("_angular_initial_state", ":items", "root", ":items", "site-config", "portIds"):
        node = node.get(key) if isinstance(node, dict) else None
    ids = (
        [part.strip() for part in node.split(",") if part.strip()] if isinstance(node, str) else []
    )
    if not ids:
        raise IssuerUnavailable("vanguard", "portIds missing in the page state")
    return ids


def _graphql_data(response: Response, operation: str) -> dict[str, Any]:
    data = ok_json("vanguard", response)
    if not isinstance(data, dict) or data.get("errors") or not isinstance(data.get("data"), dict):
        raise IssuerUnavailable("vanguard", f"GraphQL {operation} answered with errors")
    result: dict[str, Any] = data["data"]
    return result


def _parse_funds(response: Response) -> list[Any]:
    funds = _graphql_data(response, "FundsQuery").get("funds")
    if not isinstance(funds, list):
        raise IssuerUnavailable("vanguard", "funds missing in the FundsQuery answer")
    return funds


def _port_id_of(funds: list[Any], isin: str) -> str | None:
    """The portId of the fund whose identifiers carry this ISIN, None when no fund does."""
    for fund in funds:
        if not isinstance(fund, dict):
            continue
        identifiers = as_dict(fund.get("profile")).get("identifiers")
        if not isinstance(identifiers, list):
            continue
        if any(isinstance(i, dict) and i.get("altIdValue") == isin for i in identifiers):
            port_id = fund.get("portId")
            if isinstance(port_id, bool) or not isinstance(port_id, (str, int)):
                raise IssuerUnavailable("vanguard", "portId missing for the fund")
            if not str(port_id).strip():
                raise IssuerUnavailable("vanguard", "portId missing for the fund")
            return str(port_id)
    return None


class _Page:
    """One page of holdings: the fund profile, the rows read, their dates, the next key."""

    def __init__(
        self, profile: dict[str, Any], holdings: list[Holding], dates: list[str], key: Any
    ) -> None:
        self.profile = profile
        self.holdings = holdings
        self.dates = dates
        self.key = key


def _parse_holdings(response: Response) -> _Page:
    data = _graphql_data(response, "FundsHoldingsQuery")
    funds = data.get("funds")
    profile = as_dict(funds[0]) if isinstance(funds, list) and funds else {}
    blocks = data.get("borHoldings")
    block = as_dict(blocks[0]).get("holdings") if isinstance(blocks, list) and blocks else None
    items = block.get("items") if isinstance(block, dict) else None
    if not isinstance(block, dict) or not isinstance(items, list):
        raise IssuerUnavailable("vanguard", "holdings path missing in the answer")
    holdings: list[Holding] = []
    dates: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        weight = number(item.get("marketValuePercentage"))
        name = item.get("issuerName") or item.get("securityLongDescription")
        if weight is None or not name:
            continue
        date = iso_date(item.get("effectiveDate"))
        if date is not None:
            dates.append(date)
        holdings.append(
            make_holding(
                str(name),
                weight,
                ticker=item.get("ticker"),
                country=item.get("bloombergIsoCountry"),
                sector=item.get("gicsSectorDescription") or item.get("icbSectorDescription"),
                asset_class=item.get("securityType"),
            )
        )
    return _Page(as_dict(profile.get("profile")), holdings, dates, block.get("lastItemKey"))


class VanguardIssuer:
    """Adapter for Vanguard UCITS ETFs and funds listed on the German site."""

    name = "vanguard"

    def _graphql(
        self,
        http: Transport,
        operation: str,
        query: str,
        variables: dict[str, Any],
        ttl: float,
        parse: Callable[[Response], T],
    ) -> tuple[Response, T]:
        body = {"operationName": operation, "variables": variables, "query": query}
        return fetch_parsed(
            self.name, http, "POST", GRAPHQL_URL, parse, json=body, headers=HEADERS, ttl=ttl
        )

    def fetch(self, isin: str, http: Transport) -> Fund:
        """Find the portfolio id of the ISIN, then page through its holdings."""
        page, port_ids = fetch_parsed(
            self.name, http, "GET", PRODUCTS_URL, _parse_page, ttl=INDEX_TTL
        )
        funds_answer, funds = self._graphql(
            http, "FundsQuery", FUNDS_QUERY, {"portIds": port_ids}, INDEX_TTL, _parse_funds
        )
        port_id = _port_id_of(funds, isin)
        if port_id is None:
            raise NotListed(self.name, isin, "not in the Vanguard fund list")

        answers = [page, funds_answer]
        holdings: list[Holding] = []
        profile: dict[str, Any] = {}
        dates: list[str] = []
        key: Any = None  # sent back exactly as the previous page returned it
        for _ in range(MAX_PAGES):
            answer, parsed = self._graphql(
                http,
                "FundsHoldingsQuery",
                HOLDINGS_QUERY,
                {"portIds": [port_id], "lastItemKey": key},
                HOLDINGS_TTL,
                _parse_holdings,
            )
            answers.append(answer)
            profile = profile or parsed.profile
            holdings.extend(parsed.holdings)
            dates.extend(parsed.dates)
            key = parsed.key
            if not key:
                break
        else:
            raise IssuerUnavailable(self.name, f"more than {MAX_PAGES} pages of holdings")
        return Fund(
            isin=isin,
            issuer=self.name,
            fund_name=text(profile.get("fundFullName")),
            as_of=max(dates) if dates else None,
            currency=text(profile.get("fundCurrency")),
            source_url=GRAPHQL_URL,
            fetched_at=fetched_at(*answers),
            stale=any(a.stale for a in answers),
            holdings=require_holdings(self.name, holdings),
        )
