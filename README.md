# ucits-etf-issuer-holdings

[![ci](https://github.com/DylanMerigaud/ucits-etf-issuer-holdings/actions/workflows/ci.yml/badge.svg)](https://github.com/DylanMerigaud/ucits-etf-issuer-holdings/actions/workflows/ci.yml)
[![contract](https://github.com/DylanMerigaud/ucits-etf-issuer-holdings/actions/workflows/contract.yml/badge.svg)](https://github.com/DylanMerigaud/ucits-etf-issuer-holdings/actions/workflows/contract.yml)
[![PyPI](https://img.shields.io/pypi/v/ucits-etf-issuer-holdings)](https://pypi.org/project/ucits-etf-issuer-holdings/)
[![npm](https://img.shields.io/npm/v/ucits-etf-issuer-holdings)](https://www.npmjs.com/package/ucits-etf-issuer-holdings)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Give it the ISIN of a European (UCITS) ETF, get back **every holding the issuer itself
publishes** for that fund: name, weight, ISIN, country, sector, currency, as-of date. Python and
TypeScript, one JSON shape, six issuers: **iShares, Vanguard, Xtrackers, Amundi, SPDR, Invesco**.

It is for the people building portfolio trackers and analysis tools who need a fund's
look-through (country, sector or single-name exposure through funds) and have found that the
free sources stop at the top ten holdings, cover US funds only, or broke this year.

```sh
pip install ucits-etf-issuer-holdings        # Python 3.10+
npm install ucits-etf-issuer-holdings        # Node 20+, no runtime dependency
```

## Quickstart

<!-- harness: skip -->
```python
from ucits_etf_holdings import get_holdings

fund = get_holdings("IE00B4L5Y983")   # iShares Core MSCI World
print(fund.fund_name, fund.as_of, len(fund.holdings))
for h in fund.top(3):
    print(f"{h.weight:6.2f}  {h.country}  {h.name}")
print(fund.weights_by("country")[:3])
```

```text
iShares Core MSCI World UCITS ETF 2026-10-30 1271
  5.62  US  APPLE
  5.23  US  NVIDIA
  4.09  US  MICROSOFT
[('US', 72.63149), ('JP', 5.74119), ('GB', 3.50965)]
```

You do not need to know the issuer: the client asks each one in turn. Pass `issuer="ishares"`
to ask one directly.

### Try it offline

The package ships trimmed copies of real issuer answers. The same code runs on them without a
network, which is also how you test your own code against this library:

```python
from ucits_etf_holdings import HoldingsClient
from ucits_etf_holdings.testing import RECORDED_ISINS, recorded_transport

client = HoldingsClient(transport=recorded_transport())
for isin in RECORDED_ISINS:
    fund = client.get(isin)
    print(isin, fund.issuer, fund.as_of, len(fund.holdings), fund.fund_name)
```

### Look-through of a portfolio

```python
from ucits_etf_holdings import HoldingsClient, look_through
from ucits_etf_holdings.testing import recorded_transport

positions = {"IE00B4L5Y983": 6000, "IE00BK5BQT80": 3000, "LU0274211480": 1000}
client = HoldingsClient(transport=recorded_transport())  # drop transport= for live data
funds = {isin: client.get(isin) for isin in positions}
for country, amount in look_through(positions, funds, by="country")[:5]:
    print(country, round(amount, 2))
```

`by` is one of `country`, `sector`, `currency`, `asset_class`. Each position is spread over its
fund's holdings by weight.

### TypeScript

<!-- harness: skip -->
```ts
import { getHoldings, weightsBy } from "ucits-etf-issuer-holdings";

const fund = await getHoldings("IE00BK5BQT80"); // Vanguard FTSE All-World
console.log(fund.fund_name, fund.as_of, fund.holdings.length);
console.log(weightsBy(fund, "sector").slice(0, 3));
```

The objects are the same JSON as Python's `fund.to_dict()`, described by
[`schema/fund.schema.json`](schema/fund.schema.json). Offline replay:
`import { recordedTransport } from "ucits-etf-issuer-holdings/testing"`.

### Command line

<!-- harness: skip -->
```sh
ucits-holdings IE00B5M1WJ87 --format table
ucits-holdings IE00B4L5Y983 --by country --format csv > exposure.csv
```

## What you get

```json
{
  "isin": "IE00B4L5Y983",
  "issuer": "ishares",
  "fund_name": "iShares Core MSCI World UCITS ETF",
  "as_of": "2026-10-30",
  "currency": "USD",
  "source_url": "https://www.ishares.com/...",
  "fetched_at": "2026-11-02T09:41:12Z",
  "stale": false,
  "holdings": [
    {"name": "APPLE", "weight": 5.6239, "isin": "US0378331005", "ticker": "AAPL",
     "country": "US", "country_name": "United States", "sector": "Information Technology",
     "currency": "USD", "asset_class": "Equity"}
  ]
}
```

`weight` is a percent of the fund. `country` is an ISO 3166 alpha-2 code mapped from the
issuer's own country column (country of risk where the issuer says so). A field the issuer does
not publish is `null`, never guessed.

| Issuer | Found by | Holdings file | Fields the issuer gives | Updated |
|---|---|---|---|---|
| iShares | fund list of the German site | product data API | all | daily |
| Vanguard | fund list of the German site | GraphQL API, paged | no ISIN or currency per line | month end |
| Xtrackers | ISIN | xlsx export | no fund name | daily |
| Amundi | ISIN | product data API | all | daily |
| SPDR | fund list of the German site | xlsx export | all | daily |
| Invesco | ISIN | holdings API | no country or sector, no fund name | daily |

Measured on 2026-11-02 on one large fund per issuer: the weights sum to 99 to 100 percent, and a
country is known for 92 to 100 percent of the weight (Invesco: none, the file has no country).

## Errors and caching

- `InvalidISIN`: the check digit or the shape is wrong.
- `FundNotFound`: no issuer answered with holdings. Its `reasons` say, per issuer, whether the
  fund is not theirs (`NotListed`) or the issuer could not be asked (`IssuerUnavailable`, with
  what it answered).
- Fund lists are cached for a day and holdings for six hours under `~/.cache/ucits-etf-issuer-holdings`
  (`cache_dir=None` turns it off). When an issuer is down and an older copy exists, you get that
  copy with `fund.stale == True` rather than an error.
- Proxies: the Python client reads `HTTPS_PROXY` and `ALL_PROXY` (install `httpx[socks]` for SOCKS).

Issuers change their sites without notice. A contract test fetches one real fund per issuer
every morning ([contract workflow](.github/workflows/contract.yml)), so a moved endpoint shows up
as a red badge the same day.

## Why this one

| Option | UCITS issuers | Full holdings | By ISIN | Free, open | Maintained |
|---|---|---|---|---|---|
| **ucits-etf-issuer-holdings** | 6 | yes, the issuer's file | yes | MIT | daily contract tests |
| [etf-scraper](https://pypi.org/project/etf-scraper/) | no (US providers) | yes | by ticker | yes | last release 2025-03 |
| justETF based scrapers (justetf-scraping, Apify actors) | yes | top 10 | yes | varies | break with the site |
| [etfpy](https://pypi.org/project/etfpy/), [pyetfdb-scraper](https://pypi.org/project/pyetfdb-scraper/) | no (etfdb.com, US) | top holdings | by ticker | yes | |
| [OpenBB](https://github.com/OpenBB-finance/OpenBB) | no (US providers) | provider dependent | by ticker | yes | yes |
| Trackinsight | yes | yes | yes | no, behind a firewall that broke [Ghostfolio's enhancer](https://github.com/ghostfolio/ghostfolio/issues/5924) | |
| [wealthfolio/asset-profiles](https://github.com/wealthfolio/asset-profiles) | partly | aggregated | by ticker | data CC-BY-NC-SA | last push 2026-05 |
| Intrinio, FactSet, Eulerpool | yes | yes | yes | paid | yes |

The usual workaround is a hand-kept map of issuer endpoints inside each app (see
[Aurelio's issuers.py](https://github.com/LosaLosSantos/aurelio-finance/blob/main/backend/app/issuers.py)).
This library is that map, shared, tested every day, in the two languages the trackers are
written in.

## Notes

- **Swap based ETFs** (for example "Amundi MSCI World Swap") publish their substitute basket,
  not the index they track. The file is returned as published; check the fund name.
- **Terms of use**: these are the files each issuer serves to any visitor of its public product
  pages. The library fetches one file per fund on demand, caches it, and identifies itself in
  its user agent. You are responsible for respecting each issuer's website terms in your use.
- Not investment data you can rely on for trading decisions: see each issuer's disclaimer.

## Contributing

Issuer moved something, or you want another issuer? See [CONTRIBUTING.md](CONTRIBUTING.md). The
endpoints and the shape of every answer are documented in [docs/PLAN.md](docs/PLAN.md).

## License

MIT
