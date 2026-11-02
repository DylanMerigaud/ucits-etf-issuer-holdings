from __future__ import annotations

from typing import Any

import pytest
from stubs import RewritingTransport, with_json

from ucits_etf_issuer_holdings.errors import IssuerUnavailable, NotListed
from ucits_etf_issuer_holdings.http import Response
from ucits_etf_issuer_holdings.issuers.vanguard import VanguardIssuer
from ucits_etf_issuer_holdings.testing import RecordedTransport, recorded_transport


def test_fund_with_two_pages() -> None:
    transport = recorded_transport()
    fund = VanguardIssuer().fetch("IE00BK5BQT80", transport)
    assert fund.issuer == "vanguard"
    assert fund.fund_name == "Vanguard FTSE All-World UCITS ETF (USD) Accumulating"
    assert fund.currency == "USD"
    assert fund.as_of == "2026-09-30"
    assert len(fund.holdings) == 25
    first = fund.holdings[0]
    assert (first.name, first.weight, first.ticker) == ("NVIDIA Corp", 5.0056, "NVDA")
    assert (first.country, first.country_name) == ("US", "United States")
    assert first.sector == "Information Technology"
    assert (first.asset_class, first.asset_class_raw) == ("equity", "EQ.STOCK")
    assert first.isin is None
    posts = [r for r in transport.requests if r[0] == "POST"]
    assert len(posts) == 3  # funds lookup, two holdings pages


def test_not_listed() -> None:
    with pytest.raises(NotListed):
        VanguardIssuer().fetch("IE00B4L5Y983", recorded_transport())


def test_graphql_errors_are_unavailable() -> None:
    transport = RecordedTransport()
    real = transport.request

    def request(method: str, url: str, **kw: Any) -> Response:
        answer = real(method, url, **kw)
        if kw.get("json") and kw["json"].get("operationName") == "FundsHoldingsQuery":
            return with_json(answer, {"errors": [{"message": "boom"}]})
        return answer

    transport.request = request  # type: ignore[method-assign]
    with pytest.raises(IssuerUnavailable):
        VanguardIssuer().fetch("IE00BK5BQT80", transport)


def test_missing_port_ids_is_unavailable() -> None:
    def rewrite(method: str, url: str, answer: Response) -> Response:
        if method == "GET":
            return Response(200, b"<html>nothing here</html>", "text/html", url)
        return answer

    with pytest.raises(IssuerUnavailable):
        VanguardIssuer().fetch("IE00BK5BQT80", RewritingTransport(rewrite))


def test_page_guard_stops_endless_pagination() -> None:
    key = (
        '{"skey":0.00685,"portIdKey":"fundBorHoldings-9679-2026-09-30",'
        '"pkey":"fundBorHoldings-9679-2749182406ef074029f5bbdaff29301f508db9dc"}'
    )

    def rewrite(method: str, url: str, answer: Response) -> Response:
        data = answer.json() if answer.content_type == "application/json" else None
        if data and "borHoldings" in data.get("data", {}):
            data["data"]["borHoldings"][0]["holdings"]["lastItemKey"] = key
            return with_json(answer, data)
        return answer

    transport = RewritingTransport(rewrite)
    with pytest.raises(IssuerUnavailable, match="20 pages"):
        VanguardIssuer().fetch("IE00BK5BQT80", transport)
    assert transport.calls == 2 + 20  # page, funds lookup, then 20 holdings pages
