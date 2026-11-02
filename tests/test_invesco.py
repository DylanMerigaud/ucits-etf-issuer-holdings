from __future__ import annotations

import pytest
from stubs import StaticTransport

from ucits_etf_holdings.errors import IssuerUnavailable, NotListed
from ucits_etf_holdings.http import Response
from ucits_etf_holdings.issuers.invesco import InvescoIssuer
from ucits_etf_holdings.testing import recorded_transport


def test_fund() -> None:
    fund = InvescoIssuer().fetch("IE000716YHJ7", recorded_transport())
    assert fund.issuer == "invesco"
    assert fund.fund_name is None
    assert fund.as_of == "2026-10-30"
    assert len(fund.holdings) == 20
    first = fund.holdings[0]
    assert (first.name, first.weight, first.isin, first.currency) == (
        "APPLE INC USD0.00001",
        4.74,
        "US0378331005",
        "USD",
    )
    assert first.country is None and first.sector is None
    assert "&amp;" not in " ".join(h.name for h in fund.holdings)
    assert any(h.name == "ELI LILLY & CO NPV" for h in fund.holdings)


def test_sends_origin_header() -> None:
    transport = StaticTransport(Response(200, b"{}", "application/json", "u"))
    with pytest.raises(NotListed):
        InvescoIssuer().fetch("IE000716YHJ7", transport)
    headers = transport.requests[0][4]
    assert headers == {"Origin": "https://www.invesco.com"}
    assert transport.requests[0][2] == {"idType": "isin"}


def test_empty_object_and_404_are_not_listed() -> None:
    with pytest.raises(NotListed):
        InvescoIssuer().fetch(
            "IE00B4L5Y983", StaticTransport(Response(200, b"{}", "application/json", "u"))
        )
    with pytest.raises(NotListed):
        InvescoIssuer().fetch(
            "IE00B4L5Y983", StaticTransport(Response(404, b"", "text/plain", "u"))
        )


def test_406_is_unavailable() -> None:
    with pytest.raises(IssuerUnavailable):
        InvescoIssuer().fetch(
            "IE00B4L5Y983", StaticTransport(Response(406, b"", "text/plain", "u"))
        )


def test_holdings_not_a_list_is_unavailable() -> None:
    body = b'{"holdings": {"oops": 1}}'
    with pytest.raises(IssuerUnavailable):
        InvescoIssuer().fetch(
            "IE00B4L5Y983", StaticTransport(Response(200, body, "application/json", "u"))
        )
