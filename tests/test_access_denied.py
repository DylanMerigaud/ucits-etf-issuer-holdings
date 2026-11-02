"""A site that refuses the caller's network address (iShares behind Akamai, from a datacenter).

0.1.0 reported this as a bare `FundNotFound` ("ishares: HTTP 403 from ..."), which read like a
library bug. The refusal is now `AccessDenied`, named as such, and `FundNotFound.blocked` says the
fund may belong to the issuer that refused.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from stubs import StaticTransport

from ucits_etf_issuer_holdings import AccessDenied, HoldingsClient, get_holdings
from ucits_etf_issuer_holdings.cli import main
from ucits_etf_issuer_holdings.errors import FundNotFound, IssuerUnavailable, TransportError
from ucits_etf_issuer_holdings.http import CachingTransport, HttpxTransport, Response
from ucits_etf_issuer_holdings.issuers.ishares import INDEX_URL, ISharesIssuer
from ucits_etf_issuer_holdings.issuers.spdr import SpdrIssuer
from ucits_etf_issuer_holdings.issuers.vanguard import VanguardIssuer
from ucits_etf_issuer_holdings.testing import RecordedTransport

# The body Akamai sent to this library from an OVH address on 2026-11-02 (reference trimmed).
AKAMAI_403 = (
    b"<HTML><HEAD>\n<TITLE>Access Denied</TITLE>\n</HEAD><BODY>\n<H1>Access Denied</H1>\n \n"
    b'You don\'t have permission to access "http&#58;&#47;&#47;www&#46;ishares&#46;com&#47;" '
    b"on this server.<P>\nReference&#32;&#35;18&#46;0\n<P>https&#58;&#47;&#47;errors&#46;"
    b"edgesuite&#46;net&#47;18&#46;0</P>\n</BODY>\n</HTML>\n"
)


def refused(url: str = INDEX_URL) -> Response:
    return Response(403, AKAMAI_403, "text/html", url)


class BlockedHost(RecordedTransport):
    """Replays the recorded answers, except that one host answers Akamai's 403."""

    def __init__(self, host: str) -> None:
        super().__init__()
        self.host = host

    def request(self, method: str, url: str, **kw: Any) -> Response:
        if self.host in url:
            return refused(url)
        return super().request(method, url, **kw)


@pytest.mark.parametrize("issuer", [ISharesIssuer(), VanguardIssuer(), SpdrIssuer()])
def test_a_403_is_access_denied_naming_the_cause(issuer: Any) -> None:
    with pytest.raises(AccessDenied) as info:
        issuer.fetch("IE00B4L5Y983", StaticTransport(refused()))
    error = info.value
    assert isinstance(error, IssuerUnavailable)  # 0.1.0 callers catching this still do
    assert error.issuer == issuer.name
    assert error.url == INDEX_URL
    assert "refused this network address" in str(error)
    assert "datacenter" in error.reason and "proxy" in error.reason


def test_other_statuses_stay_issuer_unavailable() -> None:
    with pytest.raises(IssuerUnavailable) as info:
        ISharesIssuer().fetch("IE00B4L5Y983", StaticTransport(replace(refused(), status=503)))
    assert not isinstance(info.value, AccessDenied)


def test_fund_not_found_says_which_issuer_refused() -> None:
    client = HoldingsClient(transport=BlockedHost("ishares.com"), cache_dir=None)
    with pytest.raises(FundNotFound) as info:
        client.get("IE00B4L5Y983")
    error = info.value
    assert error.blocked == ("ishares",)
    assert str(error).startswith(
        "IE00B4L5Y983: no issuer returned holdings, and ishares refused this network address"
    )
    assert "datacenter" in error.reasons["ishares"]
    assert "not listed" in error.reasons["invesco"] or "404" in error.reasons["invesco"]


def test_other_issuers_still_answer_when_one_refuses() -> None:
    fund = HoldingsClient(transport=BlockedHost("ishares.com"), cache_dir=None).get("IE00BK5BQT80")
    assert fund.issuer == "vanguard"


def test_nothing_blocked_keeps_the_plain_message() -> None:
    with pytest.raises(FundNotFound) as info:
        HoldingsClient(transport=RecordedTransport(), cache_dir=None).get("US0378331005")
    assert info.value.blocked == ()
    assert str(info.value).startswith("US0378331005: no issuer returned holdings (")


def test_a_cached_copy_is_served_stale_on_access_denied(tmp_path: Any) -> None:
    now = [1_000_000.0]
    warm = CachingTransport(RecordedTransport(), tmp_path, clock=lambda: now[0])
    HoldingsClient(transport=warm, cache_dir=None).get("IE00B4L5Y983")
    now[0] += 7 * 24 * 3600  # past every time to live
    blocked = CachingTransport(BlockedHost("ishares.com"), tmp_path, clock=lambda: now[0])
    fund = HoldingsClient(transport=blocked, cache_dir=None).get("IE00B4L5Y983")
    assert (fund.issuer, fund.stale) == ("ishares", True)


def test_proxy_reaches_the_network_layer() -> None:
    # Nothing listens on port 9: the error proves the request went to the proxy, not the site.
    transport = HttpxTransport(timeout=5, proxy="http://127.0.0.1:9")
    with pytest.raises(TransportError):
        transport.request("GET", "https://www.ishares.com/")
    transport.close()
    with pytest.raises(FundNotFound) as info:
        get_holdings("IE00B4L5Y983", issuer="ishares", proxy="http://127.0.0.1:9", cache_dir=None)
    assert "network error" in info.value.reasons["ishares"]


def test_proxy_and_transport_are_exclusive() -> None:
    with pytest.raises(ValueError):
        HoldingsClient(transport=RecordedTransport(), proxy="http://127.0.0.1:9")


def test_cli_proxy_option(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["IE00B4L5Y983", "--issuer", "ishares", "--no-cache", "--proxy", "http://127.0.0.1:9"]
    )
    assert code == 1
    assert "network error" in capsys.readouterr().err
