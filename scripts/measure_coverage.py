"""Measure what each issuer's file covers, on the funds the contract tests use.

For one large fund per issuer it prints the number of holdings, the sum of their weights and
the share of that weight whose line has a country. It calls the issuers' sites, without the
cache; set ALL_PROXY or HTTPS_PROXY to send the traffic through a proxy.

    uv run python scripts/measure_coverage.py
"""

from __future__ import annotations

from datetime import datetime, timezone

from ucits_etf_issuer_holdings import HoldingsClient, HoldingsError

FUNDS = [
    ("ishares", "IE00B4L5Y983"),
    ("vanguard", "IE00BK5BQT80"),
    ("xtrackers", "IE00BJ0KDQ92"),
    ("amundi", "IE000BI8OT95"),
    ("spdr", "IE00B5M1WJ87"),
    ("invesco", "IE000716YHJ7"),
]


def main() -> None:
    print(f"measured {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    print(
        f"{'issuer':<10} {'isin':<13} {'as of':<10} {'lines':>6} {'weight %':>9} {'country %':>10}"
    )
    with HoldingsClient(cache_dir=None) as client:
        for issuer, isin in FUNDS:
            try:
                fund = client.get(isin, issuer=issuer)
            except HoldingsError as exc:
                print(f"{issuer:<10} {isin:<13} error: {exc}")
                continue
            total = fund.total_weight
            with_country = sum(h.weight for h in fund.holdings if h.country)
            share = 100 * with_country / total if total else 0.0
            print(
                f"{issuer:<10} {isin:<13} {fund.as_of or '-':<10} {len(fund.holdings):>6} "
                f"{total:>9.2f} {share:>10.1f}"
            )


if __name__ == "__main__":
    main()
