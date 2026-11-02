# Changelog

## 0.1.1 (2026-11-02)

- iShares from a server: iShares serves its site through Akamai, which refuses most cloud and
  datacenter addresses with `403 Access Denied` whatever the request headers (measured from an
  OVH server; the same requests from a residential connection return the full holdings, so the
  endpoints did not move). 0.1.0 reported this as a plain `FundNotFound`. A 403 from an issuer
  is now `AccessDenied` (a subclass of `IssuerUnavailable`), whose message names the cause and
  the fix, and `FundNotFound.blocked` lists the issuers that refused, in Python and TypeScript.
- `proxy=` on `HoldingsClient`, `get_holdings` and `HttpxTransport`, and `--proxy` on the Python
  command line, to read iShares through an unblocked address. Node reads `HTTPS_PROXY` with
  `NODE_USE_ENV_PROXY=1`.
- The README quickstart and the live examples use funds every issuer serves from a server
  (Vanguard FTSE All-World, SPDR, Xtrackers); a test keeps iShares funds out of them, and a
  contract test runs every fund the docs name against the live sites. The live contract tests
  skip an issuer that refuses the runner's address, with the `AccessDenied` message, instead of
  failing.
- UBS: not covered. Its ETF pages offer no public per-fund holdings file we could find; the
  README's coverage table says so.

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
