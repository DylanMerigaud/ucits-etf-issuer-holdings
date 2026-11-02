"""SPDR (State Street): fund finder for the ISIN and ticker, then the daily holdings xlsx."""

from __future__ import annotations

import re
from typing import Any

from ..errors import IssuerUnavailable, NotListed
from ..http import Transport
from ..models import Fund, Holding
from ..xlsx import read_sheet
from .base import (
    HOLDINGS_TTL,
    INDEX_TTL,
    call,
    clean,
    make_holding,
    now_utc,
    number,
    ok_json,
    require_holdings,
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


def _find_fund(finder: Any, isin: str) -> tuple[str, str] | None:
    """The (name, ticker) of the fund whose KID links carry this ISIN."""
    try:
        funds = finder["data"]["funds"]["etfs"]["datas"]
    except (KeyError, TypeError) as exc:
        raise IssuerUnavailable("spdr", "fund list path missing in the answer") from exc
    for fund in funds:
        for group in fund.get("documentPdf") or []:
            for doc in group.get("docs") or []:
                match = _KID_ISIN.search(doc.get("path") or "")
                if match and match.group(1) == isin and fund.get("fundTicker"):
                    return str(fund.get("fundName") or ""), str(fund["fundTicker"])
    return None


class SpdrIssuer:
    """Adapter for SPDR (State Street) UCITS ETFs."""

    name = "spdr"

    def fetch(self, isin: str, http: Transport) -> Fund:
        """Find the ticker of the ISIN in the fund finder, then read the holdings xlsx."""
        finder_answer = call(
            self.name, http, "GET", FINDER_URL, params=FINDER_PARAMS, ttl=INDEX_TTL
        )
        found = _find_fund(ok_json(self.name, finder_answer), isin)
        if found is None:
            raise NotListed(self.name, isin, "not in the SPDR fund list")
        listed_name, ticker = found
        url = HOLDINGS_URL.format(slug=slug_of(ticker))
        answer = call(self.name, http, "GET", url, ttl=HOLDINGS_TTL)
        if answer.status != 200:
            raise IssuerUnavailable(self.name, f"HTTP {answer.status} from {url}")
        try:
            _, rows = read_sheet(answer.content)
        except ValueError as exc:
            raise IssuerUnavailable(self.name, f"holdings file is not an xlsx: {exc}") from exc

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
            raise IssuerUnavailable(self.name, "header row with 'Percent of Fund' not found")
        header = [clean(cell) for cell in rows[header_at]]
        try:
            at = {
                key: header.index(label)
                for key, label in (
                    ("isin", "ISIN"),
                    ("name", "Security Name"),
                    ("weight", "Percent of Fund"),
                )
            }
        except ValueError as exc:
            raise IssuerUnavailable(self.name, f"expected column missing: {exc}") from exc

        def cell(row: list[Any], label: str) -> Any:
            where = header.index(label) if label in header else None
            return row[where] if where is not None and where < len(row) else None

        holdings: list[Holding] = []
        for row in rows[header_at + 1 :]:
            weight = number(row[at["weight"]]) if at["weight"] < len(row) else None
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
        return Fund(
            isin=isin,
            issuer=self.name,
            fund_name=clean(meta.get("Fund Name:")) or clean(listed_name),
            as_of=_parse_date(meta.get("Holdings As Of:")),
            currency=None,
            source_url=url,
            fetched_at=now_utc(),
            stale=finder_answer.stale or answer.stale,
            holdings=require_holdings(self.name, holdings),
        )
