"""A changed answer shape is IssuerUnavailable (or a dropped line), never a raw Python error.

Each test replays the recorded answer of a fund with one part of it altered in memory.
"""

from __future__ import annotations

import zipfile
from collections.abc import Callable
from io import BytesIO
from typing import Any

import pytest
from stubs import RewritingTransport, with_json

from ucits_etf_issuer_holdings import HoldingsClient
from ucits_etf_issuer_holdings.errors import FundNotFound, IssuerUnavailable
from ucits_etf_issuer_holdings.http import Response
from ucits_etf_issuer_holdings.issuers import ISSUERS
from ucits_etf_issuer_holdings.models import Fund
from ucits_etf_issuer_holdings.testing import recorded_transport
from ucits_etf_issuer_holdings.xlsx import XlsxError, read_sheet

Mutate = Callable[[Any], None]


def json_rewriter(match: Callable[[str, Any], bool], mutate: Mutate) -> RewritingTransport:
    """Replays the recorded answers, mutating the JSON of those `match(url, data)` selects."""

    def rewrite(method: str, url: str, answer: Response) -> Response:
        if answer.status != 200 or "json" not in answer.content_type:
            return answer
        data = answer.json()
        if not match(url, data):
            return answer
        mutate(data)
        return with_json(answer, data)

    return RewritingTransport(rewrite)


def fetch(issuer: str, isin: str, transport: RewritingTransport) -> Fund:
    return ISSUERS[issuer].fetch(isin, transport)


def unavailable(issuer: str, isin: str, transport: RewritingTransport) -> None:
    with pytest.raises(IssuerUnavailable):
        fetch(issuer, isin, transport)


# ---------------------------------------------------------------- Vanguard

VANGUARD = "IE00BK5BQT80"


def is_funds(url: str, data: Any) -> bool:
    return "graphql" in url and "borHoldings" not in data.get("data", {})


def is_holdings(url: str, data: Any) -> bool:
    return "graphql" in url and "borHoldings" in data.get("data", {})


def set_items(value: Any) -> Mutate:
    def mutate(data: Any) -> None:
        data["data"]["borHoldings"][0]["holdings"]["items"] = value

    return mutate


def test_vanguard_items_null() -> None:
    unavailable("vanguard", VANGUARD, json_rewriter(is_holdings, set_items(None)))


def test_vanguard_items_not_a_list() -> None:
    unavailable("vanguard", VANGUARD, json_rewriter(is_holdings, set_items({"a": 1})))


def test_vanguard_bor_holdings_empty() -> None:
    def mutate(data: Any) -> None:
        data["data"]["borHoldings"] = []

    unavailable("vanguard", VANGUARD, json_rewriter(is_holdings, mutate))


def test_vanguard_profile_null_keeps_the_holdings() -> None:
    def mutate(data: Any) -> None:
        data["data"]["funds"][0]["profile"] = None

    fund = fetch("vanguard", VANGUARD, json_rewriter(is_holdings, mutate))
    assert (fund.fund_name, fund.currency, len(fund.holdings)) == (None, None, 25)


def test_vanguard_port_id_missing() -> None:
    def mutate(data: Any) -> None:
        del data["data"]["funds"][0]["portId"]

    with pytest.raises(IssuerUnavailable, match="portId"):
        fetch("vanguard", VANGUARD, json_rewriter(is_funds, mutate))


def test_vanguard_port_id_null() -> None:
    def mutate(data: Any) -> None:
        data["data"]["funds"][0]["portId"] = None

    with pytest.raises(IssuerUnavailable, match="portId"):
        fetch("vanguard", VANGUARD, json_rewriter(is_funds, mutate))


def test_vanguard_non_dict_fund_and_identifier_are_skipped() -> None:
    def mutate(data: Any) -> None:
        funds = data["data"]["funds"]
        funds[0]["profile"]["identifiers"].insert(0, None)
        funds[0]["profile"]["identifiers"].insert(0, "IE00BK5BQT80")
        funds.insert(0, None)
        funds.insert(0, 7)

    assert len(fetch("vanguard", VANGUARD, json_rewriter(is_funds, mutate)).holdings) == 25


def test_vanguard_funds_null() -> None:
    def mutate(data: Any) -> None:
        data["data"]["funds"] = None

    unavailable("vanguard", VANGUARD, json_rewriter(is_funds, mutate))


def test_vanguard_port_ids_not_a_string() -> None:
    def rewrite(method: str, url: str, answer: Response) -> Response:
        if method == "GET":
            body = answer.content.replace(b'"9679,9505,9104"', b"null")
            return Response(200, body, answer.content_type, url)
        return answer

    unavailable("vanguard", VANGUARD, RewritingTransport(rewrite))


def test_vanguard_non_dict_item_is_skipped() -> None:
    def mutate(data: Any) -> None:
        data["data"]["borHoldings"][0]["holdings"]["items"].insert(0, None)

    assert len(fetch("vanguard", VANGUARD, json_rewriter(is_holdings, mutate)).holdings) == 25


# ---------------------------------------------------------------- iShares

ISHARES = "IE00B4L5Y983"


def is_ishares_holdings(url: str, data: Any) -> bool:
    return "get-product-data" in url


def points_of(data: Any) -> Any:
    return data["componentsByNameMap"]["holdings"]["containersByNameMap"]["all"][
        "dataPointsByNameMap"
    ]


def test_ishares_points_not_a_dict() -> None:
    def mutate(data: Any) -> None:
        data["componentsByNameMap"]["holdings"]["containersByNameMap"]["all"][
            "dataPointsByNameMap"
        ] = ["x"]

    unavailable("ishares", ISHARES, json_rewriter(is_ishares_holdings, mutate))


def test_ishares_names_column_not_a_dict() -> None:
    def mutate(data: Any) -> None:
        points_of(data)["issueName"] = "x"

    unavailable("ishares", ISHARES, json_rewriter(is_ishares_holdings, mutate))


def test_ishares_null_column_reads_as_none() -> None:
    def mutate(data: Any) -> None:
        points_of(data)["isin"] = None
        points_of(data)["ticker"] = {"value": None}

    fund = fetch("ishares", ISHARES, json_rewriter(is_ishares_holdings, mutate))
    assert len(fund.holdings) == 20
    assert all(h.isin is None and h.ticker is None for h in fund.holdings)


def test_ishares_short_column_is_padded() -> None:
    def mutate(data: Any) -> None:
        points_of(data)["isin"]["value"] = points_of(data)["isin"]["value"][:1]

    fund = fetch("ishares", ISHARES, json_rewriter(is_ishares_holdings, mutate))
    assert fund.holdings[0].isin == "US0378331005"
    assert fund.holdings[1].isin is None


def test_ishares_as_of_not_a_dict() -> None:
    def mutate(data: Any) -> None:
        points_of(data)["asOfDate"] = 20261030

    fund = fetch("ishares", ISHARES, json_rewriter(is_ishares_holdings, mutate))
    assert fund.as_of is None


def test_ishares_portfolio_id_null() -> None:
    def mutate(data: Any) -> None:
        for value in data.values():
            if isinstance(value, dict) and value.get("isin") == ISHARES:
                value["portfolioId"] = None

    unavailable("ishares", ISHARES, json_rewriter(lambda url, d: "screener" in url, mutate))


def test_ishares_fund_name_not_a_string() -> None:
    def mutate(data: Any) -> None:
        for value in data.values():
            if isinstance(value, dict) and value.get("isin") == ISHARES:
                value["fundName"] = 42
                value["seriesBaseCurrencyCode"] = "  "

    fund = fetch("ishares", ISHARES, json_rewriter(lambda url, d: "screener" in url, mutate))
    assert (fund.fund_name, fund.currency) == (None, None)


# ---------------------------------------------------------------- SPDR

SPDR = "IE00B5M1WJ87"


def is_finder(url: str, data: Any) -> bool:
    return "fundfinder" in url


def test_spdr_datas_null() -> None:
    def mutate(data: Any) -> None:
        data["data"]["funds"]["etfs"]["datas"] = None

    unavailable("spdr", SPDR, json_rewriter(is_finder, mutate))


def test_spdr_funds_not_a_dict() -> None:
    def mutate(data: Any) -> None:
        data["data"]["funds"] = "x"

    unavailable("spdr", SPDR, json_rewriter(is_finder, mutate))


def test_spdr_null_entries_are_skipped() -> None:
    def mutate(data: Any) -> None:
        datas = data["data"]["funds"]["etfs"]["datas"]
        for fund in datas:
            fund["documentPdf"].insert(0, None)
            fund["documentPdf"].insert(0, {"docs": None})
            fund["documentPdf"].insert(0, {"docs": [None, {"path": 5}]})
        datas.insert(0, None)
        datas.insert(0, {"fundTicker": 3, "documentPdf": "x"})

    fund = fetch("spdr", SPDR, json_rewriter(is_finder, mutate))
    assert len(fund.holdings) == 40


# ---------------------------------------------------------------- Amundi

AMUNDI = "IE000BI8OT95"


def is_amundi(url: str, data: Any) -> bool:
    return "amundietf" in url


def test_amundi_characteristics_and_currencies_not_dicts() -> None:
    def mutate(data: Any) -> None:
        data["products"][0]["characteristics"] = "x"
        data["products"][0]["currencies"] = ["USD"]

    fund = fetch("amundi", AMUNDI, json_rewriter(is_amundi, mutate))
    assert (fund.fund_name, fund.currency, len(fund.holdings)) == (None, None, 20)


def test_amundi_fund_name_not_a_string() -> None:
    def mutate(data: Any) -> None:
        data["products"][0]["characteristics"]["SHARE_MARKETING_NAME"] = ""
        data["products"][0]["currencies"]["BASE_CURRENCY"] = 5

    fund = fetch("amundi", AMUNDI, json_rewriter(is_amundi, mutate))
    assert (fund.fund_name, fund.currency) == (None, None)


def test_amundi_composition_characteristics_not_a_dict_drops_the_line() -> None:
    def mutate(data: Any) -> None:
        rows = data["products"][0]["composition"]["compositionData"]
        rows[0]["compositionCharacteristics"] = "x"
        rows.insert(0, None)

    assert len(fetch("amundi", AMUNDI, json_rewriter(is_amundi, mutate)).holdings) == 19


def test_amundi_rows_null() -> None:
    def mutate(data: Any) -> None:
        data["products"][0]["composition"]["compositionData"] = None

    unavailable("amundi", AMUNDI, json_rewriter(is_amundi, mutate))


def test_amundi_composition_not_a_dict() -> None:
    def mutate(data: Any) -> None:
        data["products"][0]["composition"] = []

    unavailable("amundi", AMUNDI, json_rewriter(is_amundi, mutate))


def test_amundi_product_null() -> None:
    def mutate(data: Any) -> None:
        data["products"][0] = None

    unavailable("amundi", AMUNDI, json_rewriter(is_amundi, mutate))


def test_amundi_datetime_is_cut_to_its_date() -> None:
    def mutate(data: Any) -> None:
        for row in data["products"][0]["composition"]["compositionData"]:
            row["compositionCharacteristics"]["date"] = "2026-10-29T00:00:00.000Z"

    assert fetch("amundi", AMUNDI, json_rewriter(is_amundi, mutate)).as_of == "2026-10-29"


# ---------------------------------------------------------------- Invesco

INVESCO = "IE000716YHJ7"


def is_invesco(url: str, data: Any) -> bool:
    return "invesco" in url


def test_invesco_null_row_is_skipped() -> None:
    def mutate(data: Any) -> None:
        data["holdings"].insert(0, None)
        data["holdings"].insert(0, "x")

    assert len(fetch("invesco", INVESCO, json_rewriter(is_invesco, mutate)).holdings) == 20


@pytest.mark.parametrize(
    ("given", "as_of"),
    [
        ("2026-10-30T00:00:00", "2026-10-30"),
        ("2026-10-30 12:00", "2026-10-30"),
        ("30/10/2026", None),
        ("2026-10-30x", None),
        (20261030, None),
        (None, None),
    ],
)
def test_invesco_as_of_only_when_a_date(given: Any, as_of: str | None) -> None:
    def mutate(data: Any) -> None:
        data["effectiveDate"] = given

    assert fetch("invesco", INVESCO, json_rewriter(is_invesco, mutate)).as_of == as_of


# ---------------------------------------------------------------- xlsx


def workbook(sheet_xml: bytes, shared: bytes | None = None, *, deflate: bool = True) -> bytes:
    buffer = BytesIO()
    mode = zipfile.ZIP_DEFLATED if deflate else zipfile.ZIP_STORED
    with zipfile.ZipFile(buffer, "w", mode) as zf:
        zf.writestr(
            "xl/workbook.xml",
            '<workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships"><sheets><sheet name="S" r:id="rId1"/></sheets></workbook>',
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
            "</Relationships>",
        )
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        if shared is not None:
            zf.writestr("xl/sharedStrings.xml", shared)
    return buffer.getvalue()


SHARED = b"<sst><si><t>a</t></si></sst>"


@pytest.mark.parametrize("index", [b"1", b"-1", b"x"])
def test_xlsx_shared_string_index_out_of_range(index: bytes) -> None:
    sheet = b'<worksheet><sheetData><row><c r="A1" t="s"><v>' + index + b"</v></c></row>"
    sheet += b"</sheetData></worksheet>"
    with pytest.raises(XlsxError, match="shared string"):
        read_sheet(workbook(sheet, SHARED))


def test_xlsx_corrupt_deflate_stream() -> None:
    sheet = b"<worksheet><sheetData>" + b"<row/>" * 200 + b"</sheetData></worksheet>"
    data = bytearray(workbook(sheet))
    start = data.index(b"xl/worksheets/sheet1.xml") + len(b"xl/worksheets/sheet1.xml")
    for position in range(start, start + 20):
        data[position] ^= 0xFF
    with pytest.raises(XlsxError):
        read_sheet(bytes(data))


def test_xlsx_truncated_file() -> None:
    data = workbook(b"<worksheet><sheetData/></worksheet>")
    with pytest.raises(XlsxError):
        read_sheet(data[: len(data) // 2])


def test_xlsx_error_is_a_value_error() -> None:
    assert issubclass(XlsxError, ValueError)


# ---------------------------------------------------------------- client


def test_unexpected_error_in_one_issuer_does_not_stop_the_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Broken:
        name = "ishares"

        def fetch(self, isin: str, http: Any) -> Fund:
            raise KeyError("portfolioId")

    monkeypatch.setitem(ISSUERS, "ishares", Broken())
    c = HoldingsClient(transport=recorded_transport(), cache_dir=None)
    assert c.get("IE000716YHJ7").issuer == "invesco"
    with pytest.raises(FundNotFound) as info:
        c.get("US0378331005")
    assert info.value.reasons["ishares"] == "unexpected answer: KeyError: 'portfolioId'"
