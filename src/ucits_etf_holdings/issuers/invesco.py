"""Invesco: one cached JSON file per share class, requested by ISIN."""

from __future__ import annotations

import html

from ..errors import IssuerUnavailable, NotListed
from ..http import Transport
from ..models import Fund, Holding
from .base import (
    HOLDINGS_TTL,
    call,
    make_holding,
    now_utc,
    number,
    ok_json,
    require_holdings,
    with_params,
)

URL = "https://dng-api.invesco.com/cache/v1/accounts/en_GB/shareclasses/{isin}/holdings/fund"
PARAMS = {"idType": "isin"}
HEADERS = {"Origin": "https://www.invesco.com"}


class InvescoIssuer:
    """Adapter for Invesco UCITS ETFs. The file has no country, sector or fund name."""

    name = "invesco"

    def fetch(self, isin: str, http: Transport) -> Fund:
        """Read the holdings file; 404 or an answer without `holdings` means not listed."""
        url = URL.format(isin=isin)
        answer = call(self.name, http, "GET", url, params=PARAMS, headers=HEADERS, ttl=HOLDINGS_TTL)
        if answer.status == 404:
            raise NotListed(self.name, isin, "HTTP 404")
        data = ok_json(self.name, answer)
        if not isinstance(data, dict) or "holdings" not in data:
            raise NotListed(self.name, isin, "the answer has no holdings")
        rows = data["holdings"]
        if not isinstance(rows, list):
            raise IssuerUnavailable(self.name, "holdings is not a list")
        holdings: list[Holding] = []
        for row in rows:
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
        return Fund(
            isin=isin,
            issuer=self.name,
            fund_name=None,
            as_of=data.get("effectiveDate"),
            currency=None,
            source_url=with_params(url, PARAMS),
            fetched_at=now_utc(),
            stale=answer.stale,
            holdings=require_holdings(self.name, holdings),
        )
