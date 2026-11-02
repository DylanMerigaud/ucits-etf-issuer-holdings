# Changelog

## Unreleased

Both languages, same JSON.

- `asset_class` is now one closed vocabulary: `equity`, `fixed_income`, `cash`, `derivative`,
  `fund`, `real_estate`, `commodity`, `other`, or null when the issuer gives none. The new
  `asset_class_raw` keeps the issuer's own label. The JSON schema lists the values.
- `look_through(..., by="isin")` (`lookThrough(..., "isin")`): single-name concentration across
  funds; a line without an ISIN is counted under its name.
- `fetched_at` is when the issuer's file was downloaded: for a cached or stale copy the time it
  was stored, and the oldest of the answers used, no longer the time of the call.
- `as_of` is set only when the issuer gives a `YYYY-MM-DD` date (a datetime is cut to its date);
  `fund_name` and the fund `currency` only when they are a non-empty string.
- One malformed issuer answer no longer stops the lookup: a changed shape is `IssuerUnavailable`,
  and any other error is kept in `FundNotFound.reasons` as `unexpected answer: ...` while the
  next issuer is asked.
- The cache keeps a new answer only when it parses, so a broken file never replaces a good copy;
  the stale copy is also served on 403, 408 and 429. Each entry is one file, written atomically
  (the old `.body` and `.json` files are no longer read). In TypeScript, concurrent identical
  requests share one download.
- Cache rule: a transport you pass is cached only when you also pass a `cache_dir`, the default
  path included.
- Python: `HoldingsClient.close()` and `with HoldingsClient() as client:`; `get_holdings` and the
  command line close their client. `xlsx.XlsxError` (a ValueError) for any unreadable workbook.
- TypeScript: an issuer name such as `toString` is unknown, as in Python.
- `ASSET_CLASSES` and `LOOK_THROUGH_KEYS` are exported; the CSV and table output have an
  `asset_class_raw` column.
- `scripts/measure_coverage.py` prints the weight sum and country coverage of one fund per issuer.

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
