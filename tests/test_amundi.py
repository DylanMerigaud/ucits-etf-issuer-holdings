from __future__ import annotations

import pytest
from stubs import RewritingTransport, StaticTransport, with_json

from ucits_etf_holdings.errors import IssuerUnavailable, NotListed, TransportError
from ucits_etf_holdings.http import Response
from ucits_etf_holdings.issuers.amundi import AmundiIssuer
from ucits_etf_holdings.testing import RecordedTransport, recorded_transport


def test_core_fund() -> None:
    fund = AmundiIssuer().fetch("IE000BI8OT95", recorded_transport())
    assert fund.issuer == "amundi"
    assert fund.fund_name == "Amundi Core MSCI World UCITS ETF Acc"
    assert fund.currency == "USD"
    assert fund.as_of == "2026-10-29"
    assert len(fund.holdings) == 20
    first = fund.holdings[0]
    assert first.name == "APPLE INC"
    assert first.weight == pytest.approx(5.602733057395508)
    assert first.isin == "US0378331005"
    assert (first.country, first.country_name) == ("US", "United States")
    assert first.sector == "Information Technology"
    assert first.currency == "USD"
    assert first.asset_class == "EQUITY_ORDINARY"


def test_swap_fund() -> None:
    fund = AmundiIssuer().fetch("LU1681043599", recorded_transport())
    assert fund.fund_name == "Amundi MSCI World Swap UCITS ETF EUR Acc"
    assert fund.currency == "EUR"
    assert len(fund.holdings) == 20
    first = fund.holdings[0]
    assert first.name == "AIRBUS SE PARIS"
    assert first.weight == pytest.approx(7.792888583439779)
    assert first.isin == "NL0000235190"
    assert first.country == "FR"


def test_request_body() -> None:
    transport = recorded_transport()
    AmundiIssuer().fetch("IE000BI8OT95", transport)
    assert transport.requests == [
        ("POST", "https://www.amundietf.de/mapi/ProductAPI/getProductsData")
    ]


def test_not_listed_when_products_empty() -> None:
    with pytest.raises(NotListed):
        AmundiIssuer().fetch("IE00B4L5Y983", StaticTransport(_json({"products": []})))


def _json(data: object) -> Response:
    import json

    return Response(200, json.dumps(data).encode(), "application/json", "u")


def test_shape_change_is_unavailable() -> None:
    def rewrite(method: str, url: str, answer: Response) -> Response:
        data = answer.json()
        del data["products"][0]["composition"]
        return with_json(answer, data)

    with pytest.raises(IssuerUnavailable):
        AmundiIssuer().fetch("IE000BI8OT95", RewritingTransport(rewrite))


def test_unrecorded_isin_is_unavailable_not_listed() -> None:
    # the replay answers 404 "not recorded": an HTTP error, not a "not listed"
    with pytest.raises(IssuerUnavailable):
        AmundiIssuer().fetch("IE00B4L5Y983", RecordedTransport())


def test_network_error() -> None:
    with pytest.raises(IssuerUnavailable):
        AmundiIssuer().fetch("IE000BI8OT95", StaticTransport(TransportError("down")))
