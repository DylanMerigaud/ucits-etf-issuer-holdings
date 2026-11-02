from __future__ import annotations

import pytest

from ucits_etf_issuer_holdings import Fund, Holding, look_through


def fund(isin: str, rows: list[tuple[str, float, str | None]]) -> Fund:
    return Fund(
        isin=isin, issuer="x", fund_name=None, as_of=None, currency=None, source_url="u",
        fetched_at="2026-11-02T00:00:00Z", stale=False,
        holdings=tuple(Holding(name=n, weight=w, country=c) for n, w, c in rows),
    )  # fmt: skip


def test_look_through_by_country() -> None:
    funds = {
        "IE00B4L5Y983": fund("IE00B4L5Y983", [("A", 60.0, "US"), ("B", 40.0, "JP")]),
        "IE00BK5BQT80": fund("IE00BK5BQT80", [("C", 50.0, "US"), ("D", 25.0, None)]),
    }
    result = look_through({"IE00B4L5Y983": 7000, "ie00bk5bqt80": 3000}, funds, by="country")
    assert result == [("US", 4200 + 1500), ("JP", 2800), (None, 750)]


def test_missing_fund_raises() -> None:
    with pytest.raises(KeyError):
        look_through({"IE00B4L5Y983": 1}, {}, by="country")


def test_bad_key() -> None:
    with pytest.raises(ValueError):
        look_through({}, {}, by="name")


def test_look_through_by_isin_falls_back_to_the_name() -> None:
    a = Fund(
        isin="IE00B4L5Y983", issuer="x", fund_name=None, as_of=None, currency=None, source_url="u",
        fetched_at="2026-11-02T00:00:00Z", stale=False,
        holdings=(
            Holding(name="APPLE", weight=50.0, isin="US0378331005"),
            Holding(name="NVIDIA Corp", weight=30.0),
        ),
    )  # fmt: skip
    b = Fund(
        isin="IE00BK5BQT80", issuer="x", fund_name=None, as_of=None, currency=None, source_url="u",
        fetched_at="2026-11-02T00:00:00Z", stale=False,
        holdings=(
            Holding(name="APPLE INC", weight=10.0, isin="US0378331005"),
            Holding(name="NVIDIA Corp", weight=20.0),
        ),
    )  # fmt: skip
    funds = {a.isin: a, b.isin: b}
    result = look_through({a.isin: 1000, b.isin: 2000}, funds, by="isin")
    assert result == [("US0378331005", 700.0), ("NVIDIA Corp", 700.0)]


def test_look_through_by_isin_on_recorded_funds() -> None:
    from ucits_etf_issuer_holdings import HoldingsClient
    from ucits_etf_issuer_holdings.testing import recorded_transport

    client = HoldingsClient(transport=recorded_transport(), cache_dir=None)
    positions = {"IE00B4L5Y983": 1000, "IE000716YHJ7": 1000}
    funds = {isin: client.get(isin) for isin in positions}
    by_isin = dict(look_through(positions, funds, by="isin"))
    assert by_isin["US0378331005"] == pytest.approx(56.239 + 47.4)


def test_isin_is_not_a_key_of_weights_by() -> None:
    with pytest.raises(ValueError):
        fund("IE00B4L5Y983", [("A", 1.0, "US")]).weights_by("isin")
