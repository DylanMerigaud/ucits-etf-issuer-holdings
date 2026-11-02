from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from ucits_etf_issuer_holdings.xlsx import read_sheet

RECORDED = Path(__file__).parent.parent / "src/ucits_etf_issuer_holdings/testing/recorded"


def build(sheet_xml: str, shared: str | None = None, sheets: str | None = None) -> bytes:
    """A minimal workbook with one worksheet stored under a non-default file name."""
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "xl/workbook.xml",
            f'<workbook {ns} xmlns:r="{rel_ns}"><sheets>'
            + (sheets or '<sheet name="Data" sheetId="1" r:id="rId9"/>')
            + "</sheets></workbook>",
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId9" Type="{rel_ns}/worksheet" Target="worksheets/sheet7.xml"/>'
            "</Relationships>",
        )
        zf.writestr(
            "xl/worksheets/sheet7.xml",
            f"<worksheet {ns}><sheetData>{sheet_xml}</sheetData></worksheet>",
        )
        if shared is not None:
            zf.writestr("xl/sharedStrings.xml", f"<sst {ns}>{shared}</sst>")
    return buf.getvalue()


def test_cell_types_and_gaps() -> None:
    sheet = (
        '<row r="1"><c r="B1" t="s"><v>0</v></c><c r="D1"><v>1.5</v></c></row>'
        '<row r="2"><c r="A2" t="inlineStr"><is><t>inline</t></is></c>'
        '<c r="C2" t="b"><v>1</v></c><c r="E2" t="str"><v>formula text</v></c></row>'
        '<row r="3"/>'
    )
    name, rows = read_sheet(build(sheet, shared="<si><t>shared</t></si>"))
    assert name == "Data"
    assert rows[0] == [None, "shared", None, 1.5]
    assert rows[1] == ["inline", None, True, None, "formula text"]
    assert rows[2] == []


def test_shared_string_rich_text_is_joined() -> None:
    shared = "<si><r><t>ab</t></r><r><t>cd</t></r></si>"
    sheet = '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
    assert read_sheet(build(sheet, shared=shared))[1][0] == ["abcd"]


def test_not_an_xlsx() -> None:
    with pytest.raises(ValueError):
        read_sheet(b"<html>500</html>")


def test_xtrackers_namespace_prefix_and_sheet2() -> None:
    name, rows = read_sheet((RECORDED / "xtrackers/LU0274211480.xlsx").read_bytes())
    assert name == "2026-11-02"
    header = next(r for r in rows if "Name" in r)
    assert header[1:] == [
        "Name", "ISIN", "Country", "Currency", "Exchange", "Type of Security",
        "Rating", "Primary Listing", "Industry Classification", "Weighting",
    ]  # fmt: skip
    first = rows[rows.index(header) + 1]
    assert first[0] == 1.0
    assert isinstance(first[10], float)


def test_spdr_plain_workbook() -> None:
    name, rows = read_sheet((RECORDED / "spdr/spyw-gy.xlsx").read_bytes())
    assert name == "holdings"
    assert rows[0][0] == "Fund Name:"
    assert rows[1][0] == "ISIN:"
    assert rows[4] == []
    assert rows[5][0] == "ISIN"
