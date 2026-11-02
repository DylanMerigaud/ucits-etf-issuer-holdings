"""Invesco: one cached JSON file per share class, requested by ISIN."""

from __future__ import annotations

import html

from ..errors import IssuerUnavailable, NotListed
from ..http import Response, Transport
from ..models import Fund, Holding
from .base import (
    HOLDINGS_TTL,
    fetch_parsed,
    fetched_at,
    iso_date,
    make_holding,
    number,
    ok_json,
    require_holdings,
    with_params,
)

URL = "https://dng-api.invesco.com/cache/v1/accounts/en_GB/shareclasses/{isin}/holdings/fund"
PARAMS = {"idType": "isin"}
HEADERS = {"Origin": "https://www.invesco.com"}


def _parse(response: Response, isin: str) -> tuple[tuple[Holding, ...], str | None]:
    """The holdings and the as-of date; 404 or an answer without `holdings` is NotListed."""
    if response.status == 404:
        raise NotListed("invesco", isin, "HTTP 404")
    data = ok_json("invesco", response)
    if not isinstance(data, dict) or "holdings" not in data:
        raise NotListed("invesco", isin, "the answer has no holdings")
    rows = data["holdings"]
    if not isinstance(rows, list):
        raise IssuerUnavailable("invesco", "holdings is not a list")
    holdings: list[Holding] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        weight = number(row.get("weight"))
        if weight is None or not row.get("name"):
            continue
        holdings.append(
            make_holding(
                html.unescape(str(row["name"])),
                weight,
                isin=row.get("isin"),
                currency=row.get("currency"),
            )
        )
    return require_holdings("invesco", holdings), iso_date(data.get("effectiveDate"))


class InvescoIssuer:
    """Adapter for Invesco UCITS ETFs. The file has no country, sector or fund name."""

    name = "invesco"

    def fetch(self, isin: str, http: Transport) -> Fund:
        """Read the holdings file; 404 or an answer without `holdings` means not listed."""
        url = URL.format(isin=isin)
        answer, (holdings, as_of) = fetch_parsed(
            self.name,
            http,
            "GET",
            url,
            lambda response: _parse(response, isin),
            params=PARAMS,
            headers=HEADERS,
            ttl=HOLDINGS_TTL,
        )
        return Fund(
            isin=isin,
            issuer=self.name,
            fund_name=None,
            as_of=as_of,
            currency=None,
            source_url=with_params(url, PARAMS),
            fetched_at=fetched_at(answer),
            stale=answer.stale,
            holdings=holdings,
        )
