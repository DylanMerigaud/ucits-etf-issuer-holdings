# Changelog

## 0.1.0 (2026-11-02)

First release, in Python and TypeScript with the same JSON output.

- Full holdings by ISIN from six UCITS issuers: iShares, Vanguard, Xtrackers, Amundi, SPDR and
  Invesco, from the files each issuer publishes on its own site.
- One normalised row per holding: name, weight in percent, ISIN, ticker, ISO country code and
  name, sector, currency, `asset_class` in one closed vocabulary (`equity`, `fixed_income`,
  `cash`, `derivative`, `fund`, `real_estate`, `commodity`, `other`) with the issuer's own label
  in `asset_class_raw`; the fund's name, currency and as-of date. A field the issuer does not
  publish is null.
- Weights grouped by country, sector, currency or asset class, and a look-through across a
  portfolio of funds, including single-name concentration (`by="isin"`).
- A disk cache (fund lists for a day, holdings for six hours, one file per entry written
  atomically) that keeps a new answer only when it parses, and serves the last good copy, marked
  stale, when an issuer is down or blocks (5xx, 403, 408, 429). `fetched_at` is when the file
  was downloaded.
- One malformed issuer answer never stops the lookup: the next issuer is asked, and
  `FundNotFound.reasons` says what each issuer answered.
- Recorded issuer answers for tests that run offline, daily contract tests against the live
  sites, and `scripts/measure_coverage.py` for the weight and country coverage per issuer.
- A command line tool, `ucits-holdings`.
