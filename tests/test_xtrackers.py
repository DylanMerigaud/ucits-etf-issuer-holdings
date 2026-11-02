from __future__ import annotations

import io
import zipfile

import pytest
from stubs import RewritingTransport, StaticTransport

from ucits_etf_issuer_holdings.errors import IssuerUnavailable, NotListed, TransportError
from ucits_etf_issuer_holdings.http import Response
from ucits_etf_issuer_holdings.issuers.xtrackers import XtrackersIssuer
from ucits_etf_issuer_holdings.testing import recorded_transport


def test_fund() -> None:
    fund = XtrackersIssuer().fetch("LU0274211480", recorded_transport())
    assert fund.issuer == "xtrackers"
    assert fund.as_of == "2026-11-02"
    assert len(fund.holdings) == 43
    first = fund.holdings[0]
    assert first.name == "SAP"
    assert first.weight == pytest.approx(11.76506915)
    assert first.isin == "DE0007164600"
    assert (first.country, first.country_name) == ("DE", "Germany")
    assert first.currency == "EUR"
    assert first.sector == "Technology"
    assert (first.asset_class, first.asset_class_raw) == ("equity", "Equities")
    assert fund.holdings[4].name == "AIRBUS"
    assert fund.holdings[4].country == "FR"


def test_cash_lines_have_no_isin_or_country_dash() -> None:
    fund = XtrackersIssuer().fetch("LU0274211480", recorded_transport())
    euro = next(h for h in fund.holdings if h.name == "EURO CURRENCY")
    assert euro.isin is None
    assert euro.country is None
    assert (euro.asset_class, euro.asset_class_raw) == ("cash", "Cash")


def test_not_listed_when_answer_is_not_an_xlsx() -> None:
    with pytest.raises(NotListed):
        XtrackersIssuer().fetch("IE00B4L5Y983", recorded_transport())
    page = Response(500, b"<html>error</html>", "text/html", "u")
    with pytest.raises(NotListed):
        XtrackersIssuer().fetch("IE00B4L5Y983", StaticTransport(page))


def test_network_error_is_unavailable() -> None:
    with pytest.raises(IssuerUnavailable):
        XtrackersIssuer().fetch("LU0274211480", StaticTransport(TransportError("down")))


def test_xlsx_without_header_is_unavailable() -> None:
    def rewrite(method: str, url: str, answer: Response) -> Response:
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(answer.content)) as src, zipfile.ZipFile(out, "w") as dst:
            for item in src.namelist():
                data = src.read(item)
                if item.endswith("sharedStrings.xml"):
                    data = data.replace(b"Weighting", b"Other")
                dst.writestr(item, data)
        return Response(200, out.getvalue(), answer.content_type, url)

    with pytest.raises(IssuerUnavailable):
        XtrackersIssuer().fetch("LU0274211480", RewritingTransport(rewrite))
