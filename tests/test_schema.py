from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from ucits_etf_issuer_holdings import ASSET_CLASSES, HoldingsClient
from ucits_etf_issuer_holdings.testing import RECORDED_ISINS, recorded_transport

SCHEMA = json.loads((Path(__file__).parent.parent / "schema/fund.schema.json").read_text())


def test_schema_is_valid() -> None:
    Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("isin", RECORDED_ISINS)
def test_recorded_funds_validate(isin: str) -> None:
    fund = HoldingsClient(transport=recorded_transport(), cache_dir=None).get(isin)
    data: dict[str, Any] = json.loads(fund.to_json())
    Draft202012Validator(SCHEMA).validate(data)


def test_bad_documents_fail() -> None:
    fund = HoldingsClient(transport=recorded_transport(), cache_dir=None).get("IE000716YHJ7")
    validator = Draft202012Validator(SCHEMA)
    data = fund.to_dict()
    data["as_of"] = "30/10/2026"
    assert not validator.is_valid(data)
    data = fund.to_dict()
    data["extra"] = 1
    assert not validator.is_valid(data)
    data = fund.to_dict()
    data["holdings"][0]["country"] = "usa"
    assert not validator.is_valid(data)
    data = fund.to_dict()
    data["holdings"][0]["asset_class"] = "Equity"
    assert not validator.is_valid(data)


def test_schema_asset_classes_match_the_vocabulary() -> None:
    enum = SCHEMA["$defs"]["holding"]["properties"]["asset_class"]["enum"]
    assert enum == [*ASSET_CLASSES, None]


def test_schema_holding_keys_match_the_dataclass() -> None:
    from dataclasses import fields

    from ucits_etf_issuer_holdings import Holding

    keys = [f.name for f in fields(Holding)]
    assert SCHEMA["$defs"]["holding"]["required"] == keys
