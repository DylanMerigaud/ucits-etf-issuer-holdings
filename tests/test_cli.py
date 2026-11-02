from __future__ import annotations

import csv
import io
import json

import pytest

from ucits_etf_issuer_holdings.cli import HOLDING_COLUMNS, main
from ucits_etf_issuer_holdings.testing import recorded_transport


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = main(args, transport=recorded_transport())
    out = capsys.readouterr()
    return code, out.out, out.err


def test_json_default(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(["IE000716YHJ7", "--no-cache"], capsys)
    assert code == 0
    data = json.loads(out)
    assert data["isin"] == "IE000716YHJ7"
    assert data["issuer"] == "invesco"
    assert len(data["holdings"]) == 20


def test_csv(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(
        ["IE000716YHJ7", "--format", "csv", "--issuer", "invesco", "--no-cache"], capsys
    )
    assert code == 0
    rows = list(csv.DictReader(io.StringIO(out)))
    assert len(rows) == 20
    assert rows[0]["name"] == "APPLE INC USD0.00001"
    assert rows[0]["weight"] == "4.74"
    assert list(rows[0]) == list(HOLDING_COLUMNS)


def test_table(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(["IE00B4L5Y983", "--format", "table", "--no-cache"], capsys)
    assert code == 0
    assert "iShares Core MSCI World UCITS ETF" in out
    assert "APPLE" in out and "5.6239" in out


def test_by_country_json(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(["IE00B4L5Y983", "--by", "country", "--no-cache"], capsys)
    assert code == 0
    data = json.loads(out)
    assert set(data[0]) == {"country", "weight"}
    assert data[0]["country"] == "US"


def test_by_sector_table_and_csv(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(
        ["IE00B4L5Y983", "--by", "sector", "--format", "table", "--no-cache"], capsys
    )
    assert code == 0 and "sector" in out.lower()
    code, out, _ = run(["IE00B4L5Y983", "--by", "sector", "--format", "csv", "--no-cache"], capsys)
    assert out.splitlines()[0] == "sector,weight"


def test_invalid_isin(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(["nope", "--no-cache"], capsys)
    assert code == 2
    assert out == "" and "not an ISIN" in err


def test_fund_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    code, _out, err = run(["US0378331005", "--no-cache"], capsys)
    assert code == 1
    assert "ishares" in err


def test_bad_option_exits(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["IE00B4L5Y983", "--format", "xml"])
    assert info.value.code == 2


def test_a_given_transport_is_not_cached(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from ucits_etf_issuer_holdings import client as client_module

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the CLI must not cache a transport it was given")

    monkeypatch.setattr(client_module, "CachingTransport", refuse)
    code, out, _ = run(["IE000716YHJ7"], capsys)
    assert code == 0 and json.loads(out)["issuer"] == "invesco"
