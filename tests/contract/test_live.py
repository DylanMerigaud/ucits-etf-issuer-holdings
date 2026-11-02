"""Contract tests against the real issuer sites. Run with UCITS_HOLDINGS_LIVE=1.

Set UCITS_HOLDINGS_PROXY (or ALL_PROXY, HTTPS_PROXY) to send the traffic through a proxy. An issuer
that refuses this machine's address (iShares from most datacenters) is skipped with the
AccessDenied it raised; any other failure is a broken endpoint and fails.
"""

from __future__ import annotations

import os
from datetime import date, datetime

import pytest

from ucits_etf_issuer_holdings import AccessDenied, FundNotFound, HoldingsClient

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("UCITS_HOLDINGS_LIVE") != "1", reason="set UCITS_HOLDINGS_LIVE=1"
    ),
]

# (isin, issuer, whether the issuer gives a country per line, oldest as-of date accepted in days)
# Vanguard publishes month-end holdings, so its file can be a month and a half old.
FUNDS = [
    ("IE00B4L5Y983", "ishares", True, 45),
    ("IE00BK5BQT80", "vanguard", True, 75),
    ("IE00BJ0KDQ92", "xtrackers", True, 45),
    ("IE000BI8OT95", "amundi", True, 45),
    ("IE00B5M1WJ87", "spdr", True, 45),
    ("IE000716YHJ7", "invesco", False, 45),
]


@pytest.mark.parametrize(("isin", "issuer", "has_country", "max_age"), FUNDS)
def test_large_fund(isin: str, issuer: str, has_country: bool, max_age: int) -> None:
    proxy = os.environ.get("UCITS_HOLDINGS_PROXY") or None
    with HoldingsClient(cache_dir=None, proxy=proxy) as client:
        try:
            fund = client.get(isin, issuer=issuer)
        except FundNotFound as exc:
            if issuer in exc.blocked:
                pytest.skip(f"{issuer} refused this address ({AccessDenied.__name__}): {exc}")
            raise
    assert fund.issuer == issuer
    assert len(fund.holdings) >= 20
    assert 90 <= fund.total_weight <= 110
    assert fund.as_of is not None
    age = (date.today() - datetime.strptime(fund.as_of, "%Y-%m-%d").date()).days
    assert -1 <= age <= max_age, f"as_of {fund.as_of} is {age} days old"
    if has_country:
        with_country = sum(h.weight for h in fund.holdings if h.country)
        assert with_country >= 0.8 * fund.total_weight
