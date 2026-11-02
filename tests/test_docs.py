"""Every ISIN a reader runs against the live sites must work from a server too (offline check)."""

from __future__ import annotations

from pathlib import Path

import pytest
from docs_isins import DATACENTER_BLOCKED, DOCS, EXAMPLES, ISSUER_OF, documented, isins, live_text

from ucits_etf_issuer_holdings import HoldingsClient
from ucits_etf_issuer_holdings.testing import RECORDED_ISINS, recorded_transport


@pytest.mark.parametrize("path", [*DOCS, *EXAMPLES], ids=lambda p: p.name)
def test_live_isins_avoid_issuers_that_block_datacenters(path: Path) -> None:
    for isin in isins(live_text(path)):
        assert isin in ISSUER_OF, f"{path.name}: add {isin} to docs_isins.ISSUER_OF"
        issuer = ISSUER_OF[isin]
        assert issuer not in DATACENTER_BLOCKED, (
            f"{path.name} runs {isin} ({issuer}) live, and {issuer} refuses most cloud and "
            "datacenter addresses: show it on the recorded transport, or pick another fund"
        )


def test_the_issuer_map_matches_the_recorded_answers() -> None:
    client = HoldingsClient(transport=recorded_transport(), cache_dir=None)
    for isin in documented():
        assert isin in ISSUER_OF, f"add {isin} to docs_isins.ISSUER_OF"
        if isin in RECORDED_ISINS:
            assert client.get(isin).issuer == ISSUER_OF[isin]


def test_the_quickstart_is_live_and_runs_anywhere() -> None:
    quick = live_text(DOCS[0]).split("## Quickstart", 1)[1].split("###", 1)[0]
    assert isins(quick), "the quickstart names no fund"
    assert all(ISSUER_OF[code] not in DATACENTER_BLOCKED for code in isins(quick))
