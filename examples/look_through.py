"""Country exposure of a three-fund portfolio, computed from each fund's full holdings.

Runs offline: the recorded transport replays real issuer answers (trimmed) shipped with the
package. Drop `transport=` to ask the issuers for today's files.
"""

from ucits_etf_issuer_holdings import HoldingsClient, look_through
from ucits_etf_issuer_holdings.testing import recorded_transport

positions = {  # ISIN -> amount held, in any currency unit
    "IE00B4L5Y983": 6000,  # iShares Core MSCI World
    "IE00BK5BQT80": 3000,  # Vanguard FTSE All-World
    "LU0274211480": 1000,  # Xtrackers DAX
}

client = HoldingsClient(transport=recorded_transport())
funds = {isin: client.get(isin) for isin in positions}

for isin, fund in funds.items():
    name = fund.fund_name or "(the file gives no name)"
    print(f"{isin}  {fund.issuer:<9} {fund.as_of}  {len(fund.holdings):>4} holdings  {name}")

print()
for country, amount in look_through(positions, funds, by="country")[:5]:
    print(f"{country or 'unknown':<8} {amount:>9.2f}")
