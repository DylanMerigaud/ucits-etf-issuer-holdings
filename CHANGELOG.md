# Changelog

## 0.1.0 (2026-11-02)

First release, in Python and TypeScript with the same JSON output.

- Full holdings by ISIN from six UCITS issuers: iShares, Vanguard, Xtrackers, Amundi, SPDR and
  Invesco, from the files each issuer publishes on its own site.
- One normalised row per holding: name, weight in percent, ISIN, ticker, ISO country code and
  name, sector, currency, asset class; the fund's name, currency and as-of date.
- Weights grouped by country, sector, currency or asset class, and a look-through across a
  portfolio of funds.
- A disk cache (fund lists for a day, holdings for six hours) that serves the last good copy,
  marked stale, when an issuer is down.
- Recorded issuer answers for tests that run offline, and daily contract tests against the live
  sites.
- A command line tool, `ucits-holdings`.
