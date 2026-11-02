// Contract tests against the real issuer sites. Run with `UCITS_HOLDINGS_LIVE=1 npm run test:live`.
// An issuer that refuses this machine's address (iShares from most datacenters) is skipped with
// the AccessDenied it raised; any other failure is a broken endpoint and fails.
// Node's fetch honours proxies only with NODE_USE_ENV_PROXY=1 and HTTPS_PROXY / HTTP_PROXY set.
import assert from "node:assert/strict";
import { test } from "node:test";
import { FundNotFound, HoldingsClient, totalWeight } from "../dist/index.js";

const live = process.env["UCITS_HOLDINGS_LIVE"] === "1";

// [isin, issuer, whether the issuer gives a country per line, oldest as-of date accepted in days]
// Vanguard publishes month-end holdings, so its file can be a month and a half old.
const FUNDS: Array<[string, string, boolean, number]> = [
  ["IE00B4L5Y983", "ishares", true, 45],
  ["IE00BK5BQT80", "vanguard", true, 75],
  ["IE00BJ0KDQ92", "xtrackers", true, 45],
  ["IE000BI8OT95", "amundi", true, 45],
  ["IE00B5M1WJ87", "spdr", true, 45],
  ["IE000716YHJ7", "invesco", false, 45],
];

for (const [isin, issuer, hasCountry, maxAge] of FUNDS) {
  test(`live: ${issuer} ${isin}`, { skip: live ? false : "set UCITS_HOLDINGS_LIVE=1", timeout: 120_000 }, async (t) => {
    let fund;
    try {
      fund = await new HoldingsClient({ cacheDir: null }).get(isin, { issuer });
    } catch (error) {
      if (error instanceof FundNotFound && error.blocked.includes(issuer)) {
        t.skip(`${issuer} refused this address (AccessDenied): ${error.message}`);
        return;
      }
      throw error;
    }
    assert.equal(fund.issuer, issuer);
    assert.ok(fund.holdings.length >= 20, `${fund.holdings.length} holdings`);
    const total = totalWeight(fund);
    assert.ok(total >= 90 && total <= 110, `total weight ${total}`);
    assert.ok(fund.as_of !== null);
    const age = (Date.now() - Date.parse(`${fund.as_of}T00:00:00Z`)) / 86_400_000;
    assert.ok(age >= -1 && age <= maxAge, `as_of ${fund.as_of} is ${age} days old`);
    if (hasCountry) {
      const withCountry = fund.holdings.filter((h) => h.country).reduce((s, h) => s + h.weight, 0);
      assert.ok(withCountry >= 0.8 * total, `country coverage ${withCountry} of ${total}`);
    }
  });
}
