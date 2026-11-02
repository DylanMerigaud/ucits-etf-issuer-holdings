from __future__ import annotations

import pytest
from stubs import RewritingTransport, StaticTransport, with_json

from ucits_etf_issuer_holdings.errors import IssuerUnavailable, NotListed, TransportError
from ucits_etf_issuer_holdings.http import Response
from ucits_etf_issuer_holdings.issuers.ishares import ISharesIssuer
from ucits_etf_issuer_holdings.testing import recorded_transport


def test_equity_fund() -> None:
    fund = ISharesIssuer().fetch("IE00B4L5Y983", recorded_transport())
    assert fund.issuer == "ishares"
    assert fund.isin == "IE00B4L5Y983"
    assert fund.fund_name == "iShares Core MSCI World UCITS ETF"
    assert fund.as_of == "2026-10-30"
    assert fund.currency == "USD"
    assert fund.stale is False
    assert len(fund.holdings) == 20
    first = fund.holdings[0]
    assert (first.name, first.weight, first.isin) == ("APPLE", 5.6239, "US0378331005")
    assert (first.country, first.country_name) == ("US", "United States")
    assert first.ticker == "AAPL"
    assert first.sector and first.currency == "USD" and first.asset_class == "Equity"
    assert fund.holdings[17].country == "NL"
    assert "portfolioId=251882" in fund.source_url


def test_bond_fund() -> None:
    fund = ISharesIssuer().fetch("IE00B3F81409", recorded_transport())
    assert fund.fund_name == "iShares Core Global Aggregate Bond UCITS ETF"
    assert len(fund.holdings) == 12
    assert fund.holdings[0].name == "BLK ICS USD LEAF AGENCY DIST"
    assert fund.holdings[0].weight == 1.9646


def test_not_listed() -> None:
    with pytest.raises(NotListed) as info:
        ISharesIssuer().fetch("IE00BK5BQT80", recorded_transport())
    assert info.value.issuer == "ishares"


def test_unwraps_raw_display_values() -> None:
    def rewrite(method: str, url: str, answer: Response) -> Response:
        if "product-screener" in url:
            data = answer.json()
            data["251882"]["isin"] = {"r": "IE00B4L5Y983", "d": "IE00B4L5Y983"}
            return with_json(answer, data)
        return answer

    fund = ISharesIssuer().fetch("IE00B4L5Y983", RewritingTransport(rewrite))
    assert len(fund.holdings) == 20


def test_missing_path_is_unavailable() -> None:
    def rewrite(method: str, url: str, answer: Response) -> Response:
        return (
            with_json(answer, {"componentsByNameMap": {}}) if "get-product-data" in url else answer
        )

    with pytest.raises(IssuerUnavailable):
        ISharesIssuer().fetch("IE00B4L5Y983", RewritingTransport(rewrite))


def test_rows_without_weight_are_dropped() -> None:
    def rewrite(method: str, url: str, answer: Response) -> Response:
        if "get-product-data" not in url:
            return answer
        data = answer.json()
        points = data["componentsByNameMap"]["holdings"]["containersByNameMap"]["all"]
        points["dataPointsByNameMap"]["holdingPercent"]["value"][0] = None
        return with_json(answer, data)

    fund = ISharesIssuer().fetch("IE00B4L5Y983", RewritingTransport(rewrite))
    assert len(fund.holdings) == 19
    assert fund.holdings[0].name == "NVIDIA"


def test_missing_column_reads_as_none() -> None:
    def rewrite(method: str, url: str, answer: Response) -> Response:
        if "get-product-data" not in url:
            return answer
        data = answer.json()
        points = data["componentsByNameMap"]["holdings"]["containersByNameMap"]["all"]
        del points["dataPointsByNameMap"]["sectorName"]
        return with_json(answer, data)

    fund = ISharesIssuer().fetch("IE00B4L5Y983", RewritingTransport(rewrite))
    assert fund.holdings[0].sector is None


def test_network_error_and_http_error_are_unavailable() -> None:
    with pytest.raises(IssuerUnavailable):
        ISharesIssuer().fetch("IE00B4L5Y983", StaticTransport(TransportError("down")))
    with pytest.raises(IssuerUnavailable):
        ISharesIssuer().fetch("IE00B4L5Y983", StaticTransport(Response(503, b"", "text/html", "u")))
    with pytest.raises(IssuerUnavailable):
        ISharesIssuer().fetch(
            "IE00B4L5Y983", StaticTransport(Response(200, b"<html>", "text/html", "u"))
        )
