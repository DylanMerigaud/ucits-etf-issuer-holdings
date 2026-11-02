"""Xtrackers (DWS): the constituents xlsx, requested directly by ISIN."""

from __future__ import annotations

from typing import Any

from ..errors import IssuerUnavailable, NotListed
from ..http import Response, Transport
from ..models import Fund, Holding
from ..xlsx import read_sheet
from .base import (
    HOLDINGS_TTL,
    clean,
    fetch_parsed,
    fetched_at,
    iso_date,
    make_holding,
    number,
    require_holdings,
)

URL = "https://etf.dws.com/etfdata/export/GBR/ENG/excel/product/constituent/{isin}/"


def _parse(response: Response, isin: str) -> tuple[tuple[Holding, ...], str | None]:
    """The holdings and the as-of date (the sheet name); an answer not an xlsx is NotListed."""
    if not response.content.startswith(b"PK"):
        raise NotListed("xtrackers", isin, f"no constituents file (HTTP {response.status})")
    try:
        sheet_name, rows = read_sheet(response.content)
    except ValueError as exc:
        raise IssuerUnavailable("xtrackers", f"constituents file unreadable: {exc}") from exc
    header_at = next(
        (position for position, row in enumerate(rows) if "Name" in row and "Weighting" in row),
        None,
    )
    if header_at is None:
        raise IssuerUnavailable("xtrackers", "header row with 'Name' and 'Weighting' not found")
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
    return require_holdings("xtrackers", holdings), iso_date(sheet_name)


class XtrackersIssuer:
    """Adapter for Xtrackers (DWS) UCITS ETFs."""

    name = "xtrackers"

    def fetch(self, isin: str, http: Transport) -> Fund:
        """Download the constituents file; an answer that is not an xlsx means not listed."""
        url = URL.format(isin=isin)
        answer, (holdings, as_of) = fetch_parsed(
            self.name, http, "GET", url, lambda response: _parse(response, isin), ttl=HOLDINGS_TTL
        )
        return Fund(
            isin=isin,
            issuer=self.name,
            fund_name=None,
            as_of=as_of,
            currency=None,
            source_url=url,
            fetched_at=fetched_at(answer),
            stale=answer.stale,
            holdings=holdings,
        )
