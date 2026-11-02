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
