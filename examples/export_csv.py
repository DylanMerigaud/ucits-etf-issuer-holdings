"""Write one fund's holdings to a CSV file, one row per holding.

Runs offline on the recorded transport; drop `transport=` to fetch the issuer's current file.
"""

import csv
import sys

from ucits_etf_holdings import get_holdings
from ucits_etf_holdings.testing import recorded_transport

fund = get_holdings("IE00B5M1WJ87", transport=recorded_transport())  # SPDR Euro Dividend Aristocrats

writer = csv.writer(sys.stdout)
writer.writerow(["name", "isin", "weight", "country", "sector", "currency"])
for h in fund.holdings[:5]:
    writer.writerow([h.name, h.isin, h.weight, h.country, h.sector, h.currency])
print(f"... {len(fund.holdings)} rows, as of {fund.as_of}", file=sys.stderr)
