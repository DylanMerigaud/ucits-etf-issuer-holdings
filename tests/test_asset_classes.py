from __future__ import annotations

import pytest

from ucits_etf_issuer_holdings import ASSET_CLASSES, HoldingsClient
from ucits_etf_issuer_holdings.issuers.asset_classes import normalize_asset_class
from ucits_etf_issuer_holdings.testing import RECORDED_ISINS, recorded_transport

CASES = [
    ("ishares", "Equity", "equity"),
    ("ishares", "Fixed Income", "fixed_income"),
    ("ishares", "Money Market", "cash"),
    ("ishares", "Cash", "cash"),
    ("ishares", "Cash Collateral and Margins", "cash"),
    ("ishares", "FX", "derivative"),
    ("ishares", "Futures", "derivative"),
    ("ishares", "Swaps", "derivative"),
    ("ishares", "Derivative", "derivative"),
    ("ishares", "Real Estate", "real_estate"),
    ("ishares", "fixed income", "fixed_income"),
    ("ishares", "Something New", "other"),
    ("xtrackers", "Equities", "equity"),
    ("xtrackers", "Bonds", "fixed_income"),
    ("xtrackers", "Fixed Income", "fixed_income"),
    ("xtrackers", "Cash", "cash"),
    ("xtrackers", "Currency", "cash"),
    ("xtrackers", "Futures", "derivative"),
    ("xtrackers", "Swaps", "derivative"),
    ("xtrackers", "Forwards", "derivative"),
    ("xtrackers", "Funds", "fund"),
    ("xtrackers", "Mutual Fund", "fund"),
    ("xtrackers", "EQUITIES", "equity"),
    ("vanguard", "EQ.STOCK", "equity"),
    ("vanguard", "EQ.REIT", "real_estate"),
    ("vanguard", "EQ.ETF", "fund"),
    ("vanguard", "MF.MF", "fund"),
    ("vanguard", "FI.CORP", "fixed_income"),
    ("vanguard", "MM.TBILL", "cash"),
    ("vanguard", "CT.CASH", "cash"),
    ("vanguard", "CRNY", "cash"),
    ("vanguard", "DE.FUT", "derivative"),
    ("vanguard", "eq.stock", "equity"),
    ("vanguard", "XX.YY", "other"),
    ("amundi", "EQUITY_ORDINARY", "equity"),
    ("amundi", "BOND_GOV", "fixed_income"),
    ("amundi", "FIXED_INCOME", "fixed_income"),
    ("amundi", "CASH", "cash"),
    ("amundi", "CURRENCY_FORWARD", "cash"),
    ("amundi", "FUTURE_INDEX", "derivative"),
    ("amundi", "SWAP", "derivative"),
    ("amundi", "FORWARD", "derivative"),
    ("amundi", "OPTION_CALL", "derivative"),
    ("amundi", "DERIVATIVE", "derivative"),
    ("amundi", "FUND", "fund"),
    ("amundi", "ETF", "fund"),
    ("amundi", "equity_preferred", "equity"),
    ("amundi", "WARRANT", "other"),
    ("spdr", "Equity", "other"),
]


@pytest.mark.parametrize(("issuer", "raw", "expected"), CASES)
def test_mapping(issuer: str, raw: str, expected: str) -> None:
    assert normalize_asset_class(issuer, raw) == expected
    assert expected in ASSET_CLASSES


@pytest.mark.parametrize("raw", [None, "", "  ", "-"])
def test_nothing_given_is_none(raw: str | None) -> None:
    assert normalize_asset_class("ishares", raw) is None


def test_every_recorded_holding_has_a_class_from_the_vocabulary() -> None:
    client = HoldingsClient(transport=recorded_transport(), cache_dir=None)
    for isin in RECORDED_ISINS:
        for holding in client.get(isin).holdings:
            if holding.asset_class_raw is None:
                assert holding.asset_class is None
            else:
                assert holding.asset_class in ASSET_CLASSES


def test_spdr_and_invesco_give_none() -> None:
    client = HoldingsClient(transport=recorded_transport(), cache_dir=None)
    for isin in ("IE00B5M1WJ87", "IE000716YHJ7"):
        holdings = client.get(isin).holdings
        assert {(h.asset_class, h.asset_class_raw) for h in holdings} == {(None, None)}
