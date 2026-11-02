// Contract tests against the real issuer sites. Run with `UCITS_HOLDINGS_LIVE=1 npm run test:live`.
// Node's fetch honours proxies only with NODE_USE_ENV_PROXY=1 and HTTPS_PROXY / HTTP_PROXY set.
import assert from "node:assert/strict";
import { test } from "node:test";
import { HoldingsClient, totalWeight } from "../dist/index.js";

const live = process.env["UCITS_HOLDINGS_LIVE"] === "1";

// [isin, issuer, whether the issuer gives a country per line]
const FUNDS: Array<[string, string, boolean]> = [
  ["IE00B4L5Y983", "ishares", true],
  ["IE00BK5BQT80", "vanguard", true],
  ["IE00BJ0KDQ92", "xtrackers", true],
  ["IE000BI8OT95", "amundi", true],
  ["IE00B5M1WJ87", "spdr", true],
  ["IE000716YHJ7", "invesco", false],
];

for (const [isin, issuer, hasCountry] of FUNDS) {
  test(`live: ${issuer} ${isin}`, { skip: live ? false : "set UCITS_HOLDINGS_LIVE=1", timeout: 120_000 }, async () => {
    const fund = await new HoldingsClient({ cacheDir: null }).get(isin, { issuer });
    assert.equal(fund.issuer, issuer);
    assert.ok(fund.holdings.length >= 20, `${fund.holdings.length} holdings`);
    const total = totalWeight(fund);
    assert.ok(total >= 90 && total <= 110, `total weight ${total}`);
    assert.ok(fund.as_of !== null);
    const age = (Date.now() - Date.parse(`${fund.as_of}T00:00:00Z`)) / 86_400_000;
    assert.ok(age >= -1 && age <= 45, `as_of ${fund.as_of} is ${age} days old`);
    if (hasCountry) {
      const withCountry = fund.holdings.filter((h) => h.country).reduce((s, h) => s + h.weight, 0);
      assert.ok(withCountry >= 0.8 * total, `country coverage ${withCountry} of ${total}`);
    }
  });
}
