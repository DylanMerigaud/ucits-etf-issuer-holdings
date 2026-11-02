from __future__ import annotations

import io
import zipfile

import pytest
from stubs import RewritingTransport

from ucits_etf_holdings.errors import IssuerUnavailable, NotListed
from ucits_etf_holdings.http import Response
from ucits_etf_holdings.issuers.spdr import SpdrIssuer
from ucits_etf_holdings.testing import recorded_transport


def test_fund() -> None:
    fund = SpdrIssuer().fetch("IE00B5M1WJ87", recorded_transport())
    assert fund.issuer == "spdr"
    assert fund.fund_name == "State Street® SPDR® S&P® Euro Dividend Aristocrats UCITS ETF (Dist)"
    assert fund.as_of == "2026-10-30"
    assert len(fund.holdings) == 40
    first = fund.holdings[0]
    assert first.name == "Teleperformance SE"
    assert first.weight == 5.71166
    assert first.isin == "FR0000051807"
    assert (first.country, first.country_name) == ("FR", "France")
    assert first.sector == "Industrials"
    assert first.currency == "EUR"
    assert fund.holdings[-1].weight > 0
    assert fund.source_url.endswith("holdings-daily-emea-en-spyw-gy.xlsx")


def test_not_listed() -> None:
    with pytest.raises(NotListed):
        SpdrIssuer().fetch("IE00B4L5Y983", recorded_transport())


def test_listed_but_file_missing_is_unavailable() -> None:
    # the other listed fund (SPPW GY) has no recorded holdings file: the replay answers 404
    with pytest.raises(IssuerUnavailable):
        SpdrIssuer().fetch("IE00BFY0GT14", recorded_transport())


def test_file_that_is_not_xlsx_is_unavailable() -> None:
    def rewrite(method: str, url: str, answer: Response) -> Response:
        return (
            Response(200, b"<html></html>", "text/html", url) if url.endswith(".xlsx") else answer
        )

    with pytest.raises(IssuerUnavailable):
        SpdrIssuer().fetch("IE00B5M1WJ87", RewritingTransport(rewrite))


def test_xlsx_without_header_row_is_unavailable() -> None:
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets><sheet name="holdings" r:id="r1"/>'
            "</sheets></workbook>",
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="r1" Type="{rel}/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>",
        )
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="{ns}"><sheetData><row r="1"><c r="A1" t="inlineStr">'
            "<is><t>nothing</t></is></c></row></sheetData></worksheet>",
        )

    def rewrite(method: str, url: str, answer: Response) -> Response:
        return (
            Response(200, buf.getvalue(), answer.content_type, url)
            if url.endswith(".xlsx")
            else answer
        )

    with pytest.raises(IssuerUnavailable):
        SpdrIssuer().fetch("IE00B5M1WJ87", RewritingTransport(rewrite))


def test_slug() -> None:
    from ucits_etf_holdings.issuers.spdr import slug_of

    assert slug_of("SPYW GY") == "spyw-gy"
    assert slug_of("ZPRV GY^") == "zprv-gy"
