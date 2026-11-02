import json

import pytest

from ucits_etf_issuer_holdings.models import Fund, Holding


def make_fund() -> Fund:
    return Fund(
        isin="IE00B4L5Y983",
        issuer="ishares",
        fund_name="Test fund",
        as_of="2026-10-30",
        currency="USD",
        source_url="https://example.com/x",
        fetched_at="2026-11-02T10:00:00Z",
        stale=False,
        holdings=(
            Holding(
                name="A", weight=50.0, country="US", country_name="United States", sector="Tech"
            ),
            Holding(name="B", weight=30.0, country="JP", country_name="Japan", sector="Tech"),
            Holding(name="C", weight=15.0, country="US", country_name="United States", sector=None),
            Holding(name="D", weight=5.0),
        ),
    )


def test_total_weight() -> None:
    assert make_fund().total_weight == pytest.approx(100.0)


def test_weights_by_country_sorted_with_none_last() -> None:
    assert make_fund().weights_by("country") == [("US", 65.0), ("JP", 30.0), (None, 5.0)]


def test_weights_by_sector() -> None:
    assert make_fund().weights_by("sector") == [("Tech", 80.0), (None, 20.0)]


def test_weights_by_rejects_unknown_key() -> None:
    with pytest.raises(ValueError):
        make_fund().weights_by("name")


def test_top() -> None:
    top = make_fund().top(2)
    assert [h.name for h in top] == ["A", "B"]


def test_dict_roundtrip_and_json() -> None:
    fund = make_fund()
    data = fund.to_dict()
    assert list(data) == [
        "isin", "issuer", "fund_name", "as_of", "currency",
        "source_url", "fetched_at", "stale", "holdings",
    ]  # fmt: skip
    assert data["holdings"][0]["name"] == "A"
    assert Fund.from_dict(data) == fund
    assert json.loads(fund.to_json()) == data
