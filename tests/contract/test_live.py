"""Contract tests against the real issuer sites. Run with UCITS_HOLDINGS_LIVE=1.

Set ALL_PROXY or HTTPS_PROXY to send the traffic through a proxy.
"""

from __future__ import annotations

import os
from datetime import date, datetime

import pytest

from ucits_etf_issuer_holdings import HoldingsClient

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("UCITS_HOLDINGS_LIVE") != "1", reason="set UCITS_HOLDINGS_LIVE=1"
    ),
]

# (isin, issuer, whether the issuer gives a country per line)
FUNDS = [
    ("IE00B4L5Y983", "ishares", True),
    ("IE00BK5BQT80", "vanguard", True),
    ("IE00BJ0KDQ92", "xtrackers", True),
    ("IE000BI8OT95", "amundi", True),
    ("IE00B5M1WJ87", "spdr", True),
    ("IE000716YHJ7", "invesco", False),
]


@pytest.mark.parametrize(("isin", "issuer", "has_country"), FUNDS)
def test_large_fund(isin: str, issuer: str, has_country: bool) -> None:
    fund = HoldingsClient(cache_dir=None).get(isin, issuer=issuer)
    assert fund.issuer == issuer
    assert len(fund.holdings) >= 20
    assert 90 <= fund.total_weight <= 110
    assert fund.as_of is not None
    age = (date.today() - datetime.strptime(fund.as_of, "%Y-%m-%d").date()).days
    assert -1 <= age <= 45
    if has_country:
        with_country = sum(h.weight for h in fund.holdings if h.country)
        assert with_country >= 0.8 * fund.total_weight
