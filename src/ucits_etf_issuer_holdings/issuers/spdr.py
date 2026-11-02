"""SPDR (State Street): fund finder for the ISIN and ticker, then the daily holdings xlsx."""

from __future__ import annotations

import re
from typing import Any

from ..errors import IssuerUnavailable, NotListed
from ..http import Response, Transport
from ..models import Fund, Holding
from ..xlsx import read_sheet
from .base import (
    HOLDINGS_TTL,
    INDEX_TTL,
    clean,
    fetch_parsed,
    fetched_at,
    make_holding,
    number,
    ok_json,
    require_holdings,
    text,
)

FINDER_URL = "https://www.ssga.com/bin/v1/ssmp/fund/fundfinder"
FINDER_PARAMS = {
    "country": "de",
    "language": "de",
    "role": "individual",
    "product": "etfs",
    "ui": "fund-finder",
}
HOLDINGS_URL = (
    "https://www.ssga.com/library-content/products/fund-data/etfs/emea/holdings-daily-emea-en-"
    "{slug}.xlsx"
)

_KID_ISIN = re.compile(r"isin=([A-Z]{2}[A-Z0-9]{9}[0-9])")
_MONTHS = {
    name: number_
    for number_, name in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1
    )
}


def slug_of(ticker: str) -> str:
    """`SPYW GY` (or `SPYW GY^`) as `spyw-gy`."""
    return ticker.replace("^", "").strip().lower().replace(" ", "-")


def _parse_date(text: Any) -> str | None:
    """`30-Oct-2026` as `2026-10-30`."""
    match = re.fullmatch(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})", str(text or "").strip())
    if match is None or match.group(2).lower() not in _MONTHS:
        return None
    return f"{match.group(3)}-{_MONTHS[match.group(2).lower()]:02d}-{int(match.group(1)):02d}"


def _parse_finder(response: Response) -> list[Any]:
    """The fund entries of the fund finder answer."""
    node: Any = ok_json("spdr", response)
    for key in ("data", "funds", "etfs", "datas"):
        node = node.get(key) if isinstance(node, dict) else None
    if not isinstance(node, list):
        raise IssuerUnavailable("spdr", "fund list path missing in the answer")
    return node


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _find_fund(funds: list[Any], isin: str) -> tuple[str | None, str] | None:
    """The (name, ticker) of the fund whose KID links carry this ISIN."""
    for fund in funds:
        if not isinstance(fund, dict):
            continue
        ticker = text(fund.get("fundTicker"))
        for group in _list(fund.get("documentPdf")):
            docs = group.get("docs") if isinstance(group, dict) else None
            for doc in _list(docs):
                path = doc.get("path") if isinstance(doc, dict) else None
                match = _KID_ISIN.search(path) if isinstance(path, str) else None
                if match and match.group(1) == isin and ticker is not None:
                    return text(fund.get("fundName")), ticker
    return None


def _parse_holdings(response: Response) -> tuple[dict[str, Any], tuple[Holding, ...]]:
    """The labelled cells above the table (`Fund Name:` ...) and the holdings."""
    if response.status != 200:
        raise IssuerUnavailable("spdr", f"HTTP {response.status} from {response.url}")
    try:
        _, rows = read_sheet(response.content)
    except ValueError as exc:
        raise IssuerUnavailable("spdr", f"holdings file is not an xlsx: {exc}") from exc

    meta: dict[str, Any] = {}
    header_at = None
    for position, row in enumerate(rows):
        label = clean(row[0]) if row else None
        if label is not None and "Percent of Fund" in [clean(c) for c in row]:
            header_at = position
            break
        if label is not None and label.endswith(":") and len(row) > 1:
            meta[label] = row[1]
    if header_at is None:
        raise IssuerUnavailable("spdr", "header row with 'Percent of Fund' not found")
    header = [clean(cell) for cell in rows[header_at]]
    for label in ("ISIN", "Security Name"):
        if label not in header:
            raise IssuerUnavailable("spdr", f"expected column missing: {label!r} is not in list")
    weight_at = header.index("Percent of Fund")

    def cell(row: list[Any], label: str) -> Any:
        where = header.index(label) if label in header else None
        return row[where] if where is not None and where < len(row) else None

    holdings: list[Holding] = []
    for row in rows[header_at + 1 :]:
        weight = number(row[weight_at]) if weight_at < len(row) else None
        if weight is None:
            break
        holdings.append(
            make_holding(
                str(cell(row, "Security Name") or ""),
                weight,
                isin=cell(row, "ISIN"),
                country_name=cell(row, "Trade Country Name"),
                sector=cell(row, "Sector Classification"),
                currency=cell(row, "Currency"),
            )
        )
    return meta, require_holdings("spdr", holdings)


class SpdrIssuer:
    """Adapter for SPDR (State Street) UCITS ETFs."""

    name = "spdr"

    def fetch(self, isin: str, http: Transport) -> Fund:
        """Find the ticker of the ISIN in the fund finder, then read the holdings xlsx."""
        finder_answer, funds = fetch_parsed(
            self.name, http, "GET", FINDER_URL, _parse_finder, params=FINDER_PARAMS, ttl=INDEX_TTL
        )
        found = _find_fund(funds, isin)
        if found is None:
            raise NotListed(self.name, isin, "not in the SPDR fund list")
        listed_name, ticker = found
        url = HOLDINGS_URL.format(slug=slug_of(ticker))
        answer, (meta, holdings) = fetch_parsed(
            self.name, http, "GET", url, _parse_holdings, ttl=HOLDINGS_TTL
        )
        return Fund(
            isin=isin,
            issuer=self.name,
            fund_name=text(meta.get("Fund Name:")) or listed_name,
            as_of=_parse_date(meta.get("Holdings As Of:")),
            currency=None,
            source_url=url,
            fetched_at=fetched_at(finder_answer, answer),
            stale=finder_answer.stale or answer.stale,
            holdings=holdings,
        )
