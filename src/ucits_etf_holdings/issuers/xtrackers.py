"""Xtrackers (DWS): the constituents xlsx, requested directly by ISIN."""

from __future__ import annotations

import re
from typing import Any

from ..errors import IssuerUnavailable, NotListed
from ..http import Transport
from ..models import Fund, Holding
from ..xlsx import read_sheet
from .base import HOLDINGS_TTL, call, clean, make_holding, now_utc, number, require_holdings

URL = "https://etf.dws.com/etfdata/export/GBR/ENG/excel/product/constituent/{isin}/"
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class XtrackersIssuer:
    """Adapter for Xtrackers (DWS) UCITS ETFs."""

    name = "xtrackers"

    def fetch(self, isin: str, http: Transport) -> Fund:
        """Download the constituents file; an answer that is not an xlsx means not listed."""
        url = URL.format(isin=isin)
        answer = call(self.name, http, "GET", url, ttl=HOLDINGS_TTL)
        if not answer.content.startswith(b"PK"):
            raise NotListed(self.name, isin, f"no constituents file (HTTP {answer.status})")
        try:
            sheet_name, rows = read_sheet(answer.content)
        except ValueError as exc:
            raise IssuerUnavailable(self.name, f"constituents file unreadable: {exc}") from exc
        header_at = next(
            (position for position, row in enumerate(rows) if "Name" in row and "Weighting" in row),
            None,
        )
        if header_at is None:
            raise IssuerUnavailable(self.name, "header row with 'Name' and 'Weighting' not found")
        header = rows[header_at]

        def column(row: list[Any], label: str) -> Any:
            where = header.index(label) if label in header else None
            return row[where] if where is not None and where < len(row) else None

        holdings: list[Holding] = []
        for row in rows[header_at + 1 :]:
            fraction = number(column(row, "Weighting"))
            name = clean(column(row, "Name"))
            if fraction is None or name is None:
                continue
            holdings.append(
                make_holding(
                    name,
                    round(fraction * 100, 10),
                    isin=column(row, "ISIN"),
                    country_name=column(row, "Country"),
                    sector=column(row, "Industry Classification"),
                    currency=column(row, "Currency"),
                    asset_class=column(row, "Type of Security"),
                )
            )
        return Fund(
            isin=isin,
            issuer=self.name,
            fund_name=None,
            as_of=sheet_name if _DATE.fullmatch(sheet_name) else None,
            currency=None,
            source_url=url,
            fetched_at=now_utc(),
            stale=answer.stale,
            holdings=require_holdings(self.name, holdings),
        )
