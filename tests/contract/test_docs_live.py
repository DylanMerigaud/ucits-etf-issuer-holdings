"""Every fund the README files and the examples name, fetched live. Run with UCITS_HOLDINGS_LIVE=1.

UCITS_HOLDINGS_PROXY sends the requests through that proxy (HTTPS_PROXY and ALL_PROXY work too).
A fund of an issuer that refuses this machine's address (DATACENTER_BLOCKED) is skipped with the
error it raised, which must be AccessDenied: any other failure is a broken endpoint.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from docs_isins import DATACENTER_BLOCKED, ISSUER_OF, documented

from ucits_etf_issuer_holdings import FundNotFound, HoldingsClient

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("UCITS_HOLDINGS_LIVE") != "1", reason="set UCITS_HOLDINGS_LIVE=1"
    ),
]


@pytest.mark.parametrize("isin", documented())
def test_documented_fund_answers_live(isin: str) -> None:
    issuer = ISSUER_OF[isin]
    proxy = os.environ.get("UCITS_HOLDINGS_PROXY") or None
    with HoldingsClient(cache_dir=None, proxy=proxy) as client:
        try:
            fund = client.get(isin)
        except FundNotFound as exc:
            if issuer in exc.blocked and issuer in DATACENTER_BLOCKED:
                pytest.skip(f"{issuer} refused this address: {exc.reasons[issuer]}")
            raise
    assert fund.issuer == issuer
    assert len(fund.holdings) >= 20
    assert 90 <= fund.total_weight <= 110
