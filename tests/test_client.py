from __future__ import annotations

from pathlib import Path

import pytest
from stubs import StaticTransport

from ucits_etf_issuer_holdings import Fund, HoldingsClient, get_holdings
from ucits_etf_issuer_holdings.errors import FundNotFound, InvalidISIN, TransportError
from ucits_etf_issuer_holdings.http import CachingTransport, Response
from ucits_etf_issuer_holdings.testing import RECORDED_ISINS, RecordedTransport, recorded_transport


def client(**kw: object) -> HoldingsClient:
    return HoldingsClient(transport=recorded_transport(), cache_dir=None, **kw)  # type: ignore[arg-type]


@pytest.mark.parametrize("isin", RECORDED_ISINS)
def test_every_recorded_isin_answers(isin: str) -> None:
    fund = client().get(isin)
    assert fund.isin == isin
    assert len(fund.holdings) > 0
    assert fund.fetched_at.endswith("Z")


def test_issuer_of_each_recorded_isin() -> None:
    expected = {
        "IE00B4L5Y983": "ishares",
        "IE00B3F81409": "ishares",
        "IE00BK5BQT80": "vanguard",
        "LU0274211480": "xtrackers",
        "IE000BI8OT95": "amundi",
        "LU1681043599": "amundi",
        "IE00B5M1WJ87": "spdr",
        "IE000716YHJ7": "invesco",
    }
    c = client()
    assert {isin: c.get(isin).issuer for isin in expected} == expected


def test_isin_is_normalised_and_validated() -> None:
    assert client().get(" ie00b4l5y983 ").isin == "IE00B4L5Y983"
    with pytest.raises(InvalidISIN):
        client().get("nope")


def test_order_asks_ishares_first_then_vanguard_spdr_xtrackers() -> None:
    transport = RecordedTransport()
    HoldingsClient(transport=transport, cache_dir=None).get("LU0274211480")
    hosts = [url.split("/")[2] for _, url in transport.requests]
    first_seen = list(dict.fromkeys(hosts))
    assert first_seen == ["www.ishares.com", "www.de.vanguard", "www.ssga.com", "etf.dws.com"]


def test_issuer_hint_asks_only_that_issuer() -> None:
    transport = RecordedTransport()
    HoldingsClient(transport=transport, cache_dir=None).get("IE000716YHJ7", issuer="invesco")
    assert {url.split("/")[2] for _, url in transport.requests} == {"dng-api.invesco.com"}


def test_unknown_issuer_hint() -> None:
    with pytest.raises(ValueError):
        client().get("IE00B4L5Y983", issuer="nobody")


def test_issuers_restriction() -> None:
    with pytest.raises(FundNotFound) as info:
        client(issuers=["invesco"]).get("IE00B4L5Y983")
    assert list(info.value.reasons) == ["invesco"]


def test_fund_not_found_carries_one_reason_per_issuer() -> None:
    with pytest.raises(FundNotFound) as info:
        client().get("US0378331005")
    reasons = info.value.reasons
    assert list(reasons) == ["ishares", "vanguard", "spdr", "xtrackers", "amundi", "invesco"]
    assert "not in the iShares product index" in reasons["ishares"]
    assert "HTTP 404" in reasons["amundi"]


def test_issuer_unavailable_is_kept_and_next_issuer_is_asked() -> None:
    class Flaky(RecordedTransport):
        def request(self, method, url, **kw):  # type: ignore[no-untyped-def]
            if "ishares.com" in url:
                raise TransportError("down")
            return super().request(method, url, **kw)

    fund = HoldingsClient(transport=Flaky(), cache_dir=None).get("IE000716YHJ7")
    assert fund.issuer == "invesco"


def test_cache_hit_without_request(tmp_path: Path) -> None:
    transport = RecordedTransport()
    c = HoldingsClient(transport=transport, cache_dir=tmp_path)
    c.get("IE000716YHJ7", issuer="invesco")
    seen = len(transport.requests)
    c.get("IE000716YHJ7", issuer="invesco")
    assert seen == 1 and len(transport.requests) == 1


def test_stale_fallback_when_network_fails(tmp_path: Path) -> None:
    now = [1000.0]
    inner = RecordedTransport()
    cache = CachingTransport(inner, tmp_path, clock=lambda: now[0])
    first = HoldingsClient(transport=cache, cache_dir=None).get("IE000716YHJ7", issuer="invesco")
    assert first.stale is False
    now[0] += 7 * 3600
    cache = CachingTransport(
        StaticTransport(TransportError("offline")), tmp_path, clock=lambda: now[0]
    )
    again = HoldingsClient(transport=cache, cache_dir=None).get("IE000716YHJ7", issuer="invesco")
    assert again.stale is True
    assert again.holdings == first.holdings


def test_zero_holdings_is_unavailable() -> None:
    body = b'{"effectiveDate": "2026-10-30", "holdings": []}'
    transport = StaticTransport(Response(200, body, "application/json", "u"))
    with pytest.raises(FundNotFound) as info:
        HoldingsClient(transport=transport, cache_dir=None).get("IE000716YHJ7", issuer="invesco")
    assert "no holdings" in info.value.reasons["invesco"]


def test_get_holdings_function() -> None:
    fund = get_holdings(
        "IE000716YHJ7", issuer="invesco", transport=recorded_transport(), cache_dir=None
    )
    assert isinstance(fund, Fund)


def test_a_200_answer_that_does_not_parse_keeps_the_cached_copy(tmp_path: Path) -> None:
    now = [1_700_000_000.0]
    first = HoldingsClient(
        transport=CachingTransport(RecordedTransport(), tmp_path, clock=lambda: now[0]),
        cache_dir=None,
    ).get("IE000716YHJ7", issuer="invesco")
    (cache_file,) = tmp_path.glob("*.cache")
    good = cache_file.read_bytes()
    now[0] += 7 * 3600
    broken = StaticTransport(Response(200, b'{"holdings": "x"}', "application/json", "u"))
    again = HoldingsClient(
        transport=CachingTransport(broken, tmp_path, clock=lambda: now[0]), cache_dir=None
    ).get("IE000716YHJ7", issuer="invesco")
    assert again.stale is True
    assert again.holdings == first.holdings
    assert again.fetched_at == "2023-11-14T22:13:20Z"
    assert cache_file.read_bytes() == good


def test_a_200_answer_that_does_not_parse_is_not_cached(tmp_path: Path) -> None:
    broken = StaticTransport(Response(200, b'{"holdings": "x"}', "application/json", "u"))
    with pytest.raises(FundNotFound) as info:
        HoldingsClient(transport=broken, cache_dir=tmp_path).get("IE000716YHJ7", issuer="invesco")
    assert info.value.reasons["invesco"] == "holdings is not a list"
    assert not list(tmp_path.glob("*.cache"))


def test_not_listed_answer_is_cached(tmp_path: Path) -> None:
    empty = StaticTransport(Response(200, b"{}", "application/json", "u"))
    c = HoldingsClient(transport=empty, cache_dir=tmp_path)
    for _ in range(2):
        with pytest.raises(FundNotFound):
            c.get("IE000716YHJ7", issuer="invesco")
    assert len(empty.requests) == 1


def test_fetched_at_is_the_oldest_answer_used(tmp_path: Path) -> None:
    now = [1_700_000_000.0]
    cache = CachingTransport(RecordedTransport(), tmp_path, clock=lambda: now[0])
    HoldingsClient(transport=cache, cache_dir=None).get("IE00B4L5Y983", issuer="ishares")
    # seven hours on the holdings (kept six hours) are fetched again, the index (a day) is not
    now[0] += 7 * 3600
    later = HoldingsClient(transport=cache, cache_dir=None).get("IE00B4L5Y983", issuer="ishares")
    assert later.fetched_at == "2023-11-14T22:13:20Z"
    assert later.stale is False
