# ucits-etf-issuer-holdings: build plan

Goal: given the ISIN of a UCITS ETF, return the full holdings list the issuer itself publishes,
normalised to one JSON shape, from Python and from TypeScript. Six issuers: iShares (BlackRock),
Vanguard, Xtrackers (DWS), Amundi, SPDR (State Street), Invesco.

Who asked for it (read only, never contacted from this repository): Ghostfolio issue 5924 (its
Trackinsight ETF enhancer broke), Wealthfolio issue 827 (UCITS look-through), Portfolio
Performance issue 1665 (asset allocation from the holdings list), Aurelio finance (hand-maintained
issuers.py), anthropics/financial-services issue 366 (look-through concentration).

## 1. Data sources (measured 2026-11-02, every request answered 200 from a residential exit)

All requests send `User-Agent: ucits-etf-issuer-holdings/<version> (+https://github.com/DylanMerigaud/ucits-etf-issuer-holdings)`.
Every one answered with that honest user agent.

### iShares
- ISIN index: `GET https://www.ishares.com/varnish-api/blk-product-screener-server/api/v1/product-screener/product-data`
  params `country=de&language=de&siteName=de-ishares-v2&userType=individual`. JSON object keyed
  by portfolio id (string); each value has `isin`, `fundName`, `portfolioId`, `localExchangeTicker`,
  `seriesBaseCurrencyCode`, `productPageUrl`. Some values may be wrapped as `{"r": raw, "d": display}`:
  unwrap to `r`. 1,322 funds, 3.8 MB: cached for 24 h. (The old `product-screener-v3.1.jsn`
  answers "File not found" since September 2026.)
- Holdings: `GET https://www.ishares.com/varnish-api/uk-retail01-product-data/product-data/api/v2/get-product-data`
  params `appSubType=ISHARES&appType=PRODUCT_PAGE&component=holdings&locale=en_GB&portfolioId=<id>&targetSite=ishares-uk&userType=individual&excludeContent=true&includeConfig=false`.
  Path `componentsByNameMap.holdings.containersByNameMap.all.dataPointsByNameMap`, each column is
  `{"value": [...]}` (column oriented). Columns: `issueName`, `isin`, `ticker`, `holdingPercent`
  (percent), `countryOfRisk` (English name), `sectorName`, `marketCurrencyCode`, `assetClass`;
  `asOfDate` is an int `20261030`. A bond fund adds `couponRate`, `maturityDate`, `duration`.
  A missing column reads as all None. Rows with no weight are dropped.
- Not listed: the ISIN is not in the index.

### Vanguard
- Fund list: `GET https://www.de.vanguard/professionell/anlageprodukte` (HTML, about 500 KB). The
  JSON in `<script id="serverApp-state" ...>...</script>` holds
  `_angular_initial_state[":items"].root[":items"]["site-config"].portIds`, a comma separated
  string of portfolio ids (418 on 2026-11-02).
- ISINs: `POST https://www.de.vanguard/gpx/graphql`, headers `Content-Type: application/json`,
  `X-Consumer-ID: de7`, body `{"operationName": "FundsQuery", "variables": {"portIds": [...]}, "query": FUNDS_QUERY}` with
  `FUNDS_QUERY = 'query FundsQuery($portIds: [String!]!) { funds(portIds: $portIds) { portId profile { portId fundFullName fundCurrency identifiers(altIds: ["ISIN"]) { altId altIdCode altIdValue } } } }'`.
  Answer `data.funds[]`: `portId`, `profile.fundFullName`, `profile.fundCurrency`,
  `profile.identifiers[].altIdValue` (the ISIN). Page and answer cached 24 h together.
- Holdings: same URL and headers, `operationName: "FundsHoldingsQuery"`, variables
  `{"portIds": [id], "lastItemKey": null}` then the `lastItemKey` the previous page returned,
  sent back exactly as received, never parsed or rebuilt (it comes as a string holding JSON,
  `"{\"skey\":0.00685,\"portIdKey\":...}"`, which the schema types as `String`); stop when it is
  null or empty; 1500 per page; a guard of 20 pages. The query text is in
  `src/ucits_etf_issuer_holdings/issuers/vanguard.py` as `HOLDINGS_QUERY`, word for word below.
  Answer: `data.funds[0].profile` (`fundFullName`, `fundCurrency`) and
  `data.borHoldings[0].holdings` (`items`, `totalHoldings`, `lastItemKey`). Item fields:
  `issuerName`, `securityLongDescription`, `gicsSectorDescription`, `marketValuePercentage`
  (percent), `sedol1`, `ticker`, `securityType` (`EQ.STOCK`, `FI.*`, `MM.*`, ...),
  `effectiveDate` (`YYYY-MM-DD`), `bloombergIsoCountry` (ISO alpha-2). No ISIN per line.
  GraphQL `errors` in the answer: IssuerUnavailable.

```graphql
query FundsHoldingsQuery($portIds: [String!], $securityTypes: [String!], $lastItemKey: String) {
    funds(portIds: $portIds) {
      profile {
        fundFullName
        fundCurrency
        primarySectorEquityClassification
      }
    }
    borHoldings(portIds: $portIds) {
      holdings(limit: 1500, securityTypes: $securityTypes, lastItemKey: $lastItemKey) {
        items {
          issuerName
          securityLongDescription
          gicsSectorDescription
          icbSectorDescription
          icbIndustryDescription
          marketValuePercentage
          sedol1
          quantity
          ticker
          securityType
          finalMaturity
          effectiveDate
          marketValueBaseCurrency
          bloombergIsoCountry
          couponRate
        }
        totalHoldings
        lastItemKey
      }
    }
  }
```

### Xtrackers (DWS)
- Holdings by ISIN directly: `GET https://etf.dws.com/etfdata/export/GBR/ENG/excel/product/constituent/<ISIN>/`.
  An xlsx (starts with `PK`). Workbook has ONE sheet whose name is the as-of date `YYYY-MM-DD`;
  its XML uses the `x:` namespace prefix and lives in `xl/worksheets/sheet2.xml` (resolve through
  `xl/_rels/workbook.xml.rels`, never assume sheet1). Rows: a disclaimer, then the header
  `["", "Name", "ISIN", "Country", "Currency", "Exchange", "Type of Security", "Rating", "Primary Listing", "Industry Classification", "Weighting"]`,
  then data rows whose first cell is the rank. `Weighting` is a FRACTION (0.056): times 100.
- Not listed: the answer is not an xlsx (an unknown ISIN gets a 500 HTML page).

### Amundi
- `POST https://www.amundietf.de/mapi/ProductAPI/getProductsData`, body
  `{"context": {"countryCode": "DEU", "languageCode": "de", "userProfileName": "RETAIL"}, "productIds": [ISIN], "productType": "PRODUCT", "characteristics": ["SHARE_MARKETING_NAME"], "composition": {"compositionFields": ["date", "type", "isin", "name", "weight", "currency", "sector", "countryOfRisk"]}}`.
  Answer `products[0]`: `characteristics.SHARE_MARKETING_NAME`, `currencies.BASE_CURRENCY`,
  `composition.compositionData[].compositionCharacteristics` with `date`, `type`, `isin`, `name`,
  `weight` (FRACTION, times 100), `currency`, `sector`, `countryOfRisk`.
- Not listed: `products` is empty.
- Swap based funds (name contains "Swap") publish their substitute basket, not the index: said in
  the README.

### SPDR (State Street)
- Fund list: `GET https://www.ssga.com/bin/v1/ssmp/fund/fundfinder` params
  `country=de&language=de&role=individual&product=etfs&ui=fund-finder`. Answer
  `data.funds.etfs.datas[]`: `fundName`, `fundTicker` (`"SPYW GY"`, sometimes with a trailing `^`),
  `documentPdf[]` whose KID entries carry paths like `/library-content/kids?isin=IE00B5M1WJ87&...`:
  the ISIN is read with `isin=([A-Z]{2}[A-Z0-9]{9}[0-9])`. Cached 24 h.
- Holdings: `GET https://www.ssga.com/library-content/products/fund-data/etfs/emea/holdings-daily-emea-en-<slug>.xlsx`
  where slug = ticker without `^`, lower case, spaces to `-` (`spyw-gy`). Sheet `holdings`: rows
  `["Fund Name:", name]`, `["ISIN:", isin]`, `["Ticker Symbol:", ...]`, `["Holdings As Of:", "30-Oct-2026"]`,
  a blank row, then the header `ISIN, SEDOL, Security Name, Currency, Number of Shares, Percent of Fund, Trade Country Name, Local Price, Sector Classification, Industry Classification, Base Market Value`.
  `Percent of Fund` is a PERCENT. Data stops at the first row with no numeric weight.
- Not listed: the ISIN is not in the fund list.

### Invesco
- `GET https://dng-api.invesco.com/cache/v1/accounts/en_GB/shareclasses/<ISIN>/holdings/fund?idType=isin`
  with header `Origin: https://www.invesco.com` (without it: 406 empty body; adding
  `productType=ETF` also gives 406). Answer `{"effectiveDate": "2026-10-30", "numberOfHoldings": 2088, "holdings": [{"name", "isin", "weight" (percent), "currency"}]}`.
  No country, no sector, no fund name.
- Not listed: status 200 with `{}` (no `holdings` key), or 404.

### Terms of use
These are the files each issuer serves to any visitor of its public product pages. The library
fetches one file per fund on demand, caches it, and sends an identifying user agent. The README
says the user is responsible for the issuer's website terms.

## 2. Public API (Python, package `ucits_etf_issuer_holdings`, distribution `ucits-etf-issuer-holdings`)

```python
from ucits_etf_issuer_holdings import get_holdings, HoldingsClient, Fund, Holding, look_through
fund = get_holdings("IE00B4L5Y983")            # tries every issuer, cached
fund = get_holdings("IE00B4L5Y983", issuer="ishares")
fund.isin, fund.issuer, fund.fund_name, fund.as_of, fund.currency, fund.source_url
fund.fetched_at, fund.stale, fund.holdings   # tuple[Holding, ...]
fund.total_weight                            # sum of weights, percent
fund.weights_by("country")                   # [("US", 71.2), ("JP", 5.1), ..., (None, 0.3)]
fund.top(10)
fund.to_dict(); Fund.from_dict(d); fund.to_json()
look_through({"IE00B4L5Y983": 7000, "IE00BK5BQT80": 3000}, funds, by="country")  # or by="isin"
client = HoldingsClient(transport=None, cache_dir=<default>, issuers=None, timeout=30.0)
client.get(isin, issuer=None) -> Fund
client.close()   # or: with HoldingsClient() as client: ...
from ucits_etf_issuer_holdings.testing import recorded_transport, RECORDED_ISINS   # offline replay
```

Errors (`ucits_etf_issuer_holdings.errors`, all subclass `HoldingsError`): `InvalidISIN`,
`NotListed(issuer, isin, reason)`, `IssuerUnavailable(issuer, reason)`,
`FundNotFound(isin, reasons: dict[str, str])` (no issuer answered with holdings; the reasons say
why each one did not).

Holding: `name: str`, `weight: float` (percent of the fund), `isin`, `ticker`, `country`
(ISO alpha-2), `country_name`, `sector`, `currency`, `asset_class`, `asset_class_raw` (all
`str | None`). `asset_class` is one of `ASSET_CLASSES`: `equity`, `fixed_income`, `cash`,
`derivative`, `fund`, `real_estate`, `commodity`, `other` (a label not in the mapping), or None
when the issuer gives no class; `asset_class_raw` is the issuer's own label. The mapping
(`issuers/asset_classes.py`), case-insensitive: iShares `Equity` equity, `Fixed Income`
fixed_income, `Money Market`, `Cash`, `Cash Collateral and Margins` cash, `FX`, `Futures`,
`Swaps`, `Derivative` derivative, `Real Estate` real_estate; Xtrackers `Equities` equity,
`Bonds`, `Fixed Income` fixed_income, `Cash`, `Currency` cash, `Futures`, `Swaps`, `Forwards`
derivative, `Funds`, `Mutual Fund` fund; Vanguard by `securityType` prefix: `EQ.REIT`
real_estate, `EQ.ETF` fund, other `EQ.` equity, `MF.` fund, `FI.` fixed_income, `MM.`, `CT.`,
`CRNY` cash, `DE.` derivative; Amundi by `type` prefix: `EQUITY` equity, `BOND`,
`FIXED_INCOME` fixed_income, `CASH`, `CURRENCY` cash, `FUTURE`, `SWAP`, `FORWARD`, `OPTION`,
`DERIVATIVE` derivative, `FUND`, `ETF` fund. SPDR and Invesco publish no class: both None.
`country` is filled from `country_name` through `countries.to_iso2`, or directly when the issuer
gives a code (Vanguard); `country_name` from `countries.name_of` when only the code is given.

JSON schema: `schema/fund.schema.json` (draft 2020-12), keys exactly the field names above,
`as_of` `YYYY-MM-DD` or null (an issuer datetime is cut to its date; anything else is null),
`fund_name` and `currency` a non-empty string or null, `fetched_at` ISO 8601 UTC: when the
issuer's answer was downloaded, for a cached or stale copy the time it was stored, and when
several answers were used (index and holdings, Vanguard pages) the oldest. Both languages emit it.

`look_through` groups by `LOOK_THROUGH_KEYS`: the four `WEIGHT_KEYS` plus `isin` (the holding's
ISIN, or its name when it has none). `weights_by` and the CLI `--by` take the four `WEIGHT_KEYS`.

CLI: `ucits-holdings ISIN [--issuer NAME] [--format json|csv|table] [--by country|sector|currency|asset_class] [--no-cache]`.

### Internals
- `isin.py`: `normalize(isin) -> str` (strip, upper, 12 chars, `[A-Z]{2}[A-Z0-9]{9}[0-9]`, Luhn
  check digit on the letter-expanded string) raising `InvalidISIN`.
- `countries.py`: `to_iso2(text) -> str | None` (two letters that are a known code pass through;
  otherwise lookup lower-cased in `_country_data.NAME_TO_ISO2`), `name_of(code) -> str | None`.
- `http.py`: `Response` dataclass (`status`, `content: bytes`, `content_type`, `url`,
  `stale=False`, `stored_at` (epoch seconds: now for a live answer, the store time for a cached
  one), `.text`, `.json()`), `Transport` Protocol
  `request(method, url, *, params=None, json=None, headers=None, ttl=None) -> Response`,
  `HttpxTransport(timeout)` (httpx.Client, `follow_redirects=True`, trust_env so HTTPS_PROXY and
  ALL_PROXY work; network errors become `TransportError`; `close()`),
  `CachingTransport(inner, cache_dir)`: key = sha256 of method, url, sorted params, canonical
  JSON body; one file per key, `<key>.cache`, a JSON line of meta (`stored_at`, `content_type`,
  `url`) then the body, written to a temporary file and renamed into place; 200 answers only; a
  fresh copy (age < ttl) is returned without a request; when the live request raises
  `TransportError` or answers 403, 408, 429 or >= 500 and a stale copy exists, the stale copy is
  returned with `stale=True`. `request(..., validate=callable)`: a new 200 answer is stored only
  when `validate(response)` returns; when it raises, the previous copy stays and is served
  stale, or with no copy the live answer is returned unstored. `ttl=None` means no caching for
  that call. The TypeScript port shares one download between concurrent identical requests.
- `xlsx.py`: `read_sheet(data: bytes) -> tuple[str, list[list[str | float | None]]]` (sheet name,
  rows), stdlib only (zipfile, xml.etree): first sheet of `xl/workbook.xml`, its target through
  `xl/_rels/workbook.xml.rels`, shared strings, inline strings, numbers, booleans, cell
  references with gaps filled by None, any namespace prefix.
- `issuers/`: one module per issuer, each a class with `name` and
  `fetch(isin: str, http: Transport) -> Fund` raising `NotListed` or `IssuerUnavailable`. Each
  answer is read by a parse function (`base.fetch_parsed`) that checks every shape with
  isinstance before using it: a changed container is `IssuerUnavailable`, a line that is not an
  object is dropped. The same parse function is the cache's `validate` (a `NotListed` counts as
  understood), so an answer the adapter cannot read never replaces a good cached copy.
  `ORDER = ("ishares", "vanguard", "spdr", "xtrackers", "amundi", "invesco")`: the issuers
  whose answer is an index (cached a day) first, then the ones asked by ISIN.
  TTL: indexes 24 h, holdings 6 h.
- `client.py`: `HoldingsClient.get` validates the ISIN, asks the named issuer only or each issuer
  of ORDER; `NotListed` and `IssuerUnavailable` are kept as reasons and the next issuer is asked;
  any other error that is not a `HoldingsError` is kept as `unexpected answer: <type>: <message>`
  and the next issuer is asked; first holdings win; none: `FundNotFound`. A Fund with zero
  holdings is `IssuerUnavailable`. Cache rule: with no transport the client caches in
  `DEFAULT_CACHE_DIR`; a transport you pass is not cached unless you pass a `cache_dir` (any
  value, the default path included); `cache_dir=None` never caches. `close()` and the context
  manager close the httpx client the object made; `get_holdings` closes its client.
- `testing/`: `RecordedTransport` replays `testing/recorded/index.json` (entries: `method`, `url`,
  `params` or null, `match_json` or null, `status`, `content_type`, `file`). A request matches an
  entry when method and url are equal, params equal (values compared as strings) when the entry
  has params, and the entry's `match_json` is a recursive subset of the request JSON body (lists
  compared whole). Unmatched: status 404, body `not recorded`. `recorded_transport()` returns one;
  `RECORDED_ISINS` lists the ISINs it can answer: IE00B4L5Y983, IE00B3F81409 (iShares),
  IE00BK5BQT80 (Vanguard, two pages), LU0274211480 (Xtrackers), IE000BI8OT95 and LU1681043599
  (Amundi), IE00B5M1WJ87 (SPDR), IE000716YHJ7 (Invesco). The recorded files are trimmed copies
  of real answers of 2026-11-02.

## 3. TypeScript port (`js/`, npm package `ucits-etf-issuer-holdings`)

Same issuers, same endpoints, same JSON shape (the objects ARE the schema: snake_case keys,
`as_of` string). Node >= 20, ESM, zero runtime dependencies (global `fetch`, `node:zlib`
`inflateRawSync` for the xlsx zip, `node:fs` for the cache). API:
`getHoldings(isin, opts?)`, `new HoldingsClient({ transport?, cacheDir?, issuers?, timeoutMs? })`,
`client.get(isin, { issuer? })`, `weightsBy(fund, key)`, `topHoldings(fund, n)`,
`lookThrough(positions, funds, by)`, `ASSET_CLASSES`, `LOOK_THROUGH_KEYS`, errors as classes with the same names, and
`ucits-etf-issuer-holdings/testing` exporting `recordedTransport()` and `RECORDED_ISINS` over the
same recorded files (copied into `js/recorded/` by `npm run build`). Tests: `node:test` on the
compiled output, the same per issuer expectations as Python, plus a test that a Python-made JSON
and a TS-made JSON for the same recorded fund are equal apart from `fetched_at`.

## 4. Tests

- Unit tests per module, and per issuer on the recorded transport: the fund name, as-of date,
  first holding exactly (name, weight, isin, country), count of rows, pagination (Vanguard),
  NotListed for an ISIN of another issuer, IssuerUnavailable on a shape change (a JSON with the
  path missing, an xlsx with no header row).
- Client: ordering, reasons in FundNotFound, issuer hint, cache hit without a request, stale
  fallback when the network fails.
- Schema: every recorded fund's `to_dict()` validates against `schema/fund.schema.json`.
- Contract tests (`tests/contract/`, marker `live`, run when `UCITS_HOLDINGS_LIVE=1`): one per
  issuer on a large real fund (IE00B4L5Y983, IE00BK5BQT80, IE00BJ0KDQ92, IE000BI8OT95,
  IE00B5M1WJ87, IE000716YHJ7): at least 20 holdings, weights summing to 90 to 110, an as-of date
  within 45 days (75 for Vanguard, whose holdings are month end), at least 80 percent of weight
  with a country where the issuer gives one. `scripts/measure_coverage.py` prints the weight sum
  and country coverage of the same funds (the README figures come from it).
  `.github/workflows/contract.yml` runs them every day at 06:00 UTC for both languages, so an
  endpoint move turns the badge red the next morning.

## 5. Library harness criteria (growth-cockpit `scripts/oss_lib_harness.py`) and how each is met

- E1 install-built: hatchling wheel, `httpx` the only dependency; the npm tarball ships `dist/`,
  `recorded/`, types.
- E2 quickstart-runs: the README blocks that call the network are marked
  `<!-- harness: skip -->`; the offline block uses `ucits_etf_issuer_holdings.testing.recorded_transport()`
  and runs as written.
- E3 tests-green: `pytest` passes offline (live tests skipped without `UCITS_HOLDINGS_LIVE=1`).
- E4 api-typed: `py.typed`, mypy strict, every public signature annotated.
- E5 examples-run: `examples/*.py` run offline on the recorded transport.
- Measured: README quickstart importing the package, CI workflow, typed, lint config
  (`ruff.toml`). Also tests, examples, docs, changelog, license, issue templates, contributing.
- J1 what and for whom in the opening lines; J2 install line plus a runnable example with its
  output; J3 a comparison table against etf-scraper, justetf-scraping, etfpy and pyetfdb-scraper,
  OpenBB, Trackinsight, wealthfolio/asset-profiles and paid APIs.

## 6. Done criteria

1. `uv run pytest` green, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` clean.
2. `UCITS_HOLDINGS_LIVE=1 uv run pytest tests/contract` green for all six issuers (through a proxy
   from the build box).
3. `cd js && npm ci && npm run build && npm test` green; live TS contract test green.
4. Python and TS JSON equal on every recorded fund.
5. An independent review found nothing left open.
6. `oss_lib_harness.py check` says PASS.
7. Repository public, v0.1.0 tagged, PyPI and npm pages answer with 0.1.0.
