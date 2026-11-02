import assert from "node:assert/strict";
import { test } from "node:test";
import { ASSET_CLASSES, HoldingsClient } from "../dist/index.js";
import { normalizeAssetClass } from "../dist/issuers/assetClasses.js";
import { RECORDED_ISINS, recordedTransport } from "../dist/testing.js";

const CASES: Array<[string, string, string]> = [
  ["ishares", "Equity", "equity"],
  ["ishares", "Fixed Income", "fixed_income"],
  ["ishares", "Money Market", "cash"],
  ["ishares", "Cash", "cash"],
  ["ishares", "Cash Collateral and Margins", "cash"],
  ["ishares", "FX", "derivative"],
  ["ishares", "Futures", "derivative"],
  ["ishares", "Swaps", "derivative"],
  ["ishares", "Derivative", "derivative"],
  ["ishares", "Real Estate", "real_estate"],
  ["ishares", "fixed income", "fixed_income"],
  ["ishares", "Something New", "other"],
  ["xtrackers", "Equities", "equity"],
  ["xtrackers", "Bonds", "fixed_income"],
  ["xtrackers", "Fixed Income", "fixed_income"],
  ["xtrackers", "Cash", "cash"],
  ["xtrackers", "Currency", "cash"],
  ["xtrackers", "Futures", "derivative"],
  ["xtrackers", "Swaps", "derivative"],
  ["xtrackers", "Forwards", "derivative"],
  ["xtrackers", "Funds", "fund"],
  ["xtrackers", "Mutual Fund", "fund"],
  ["xtrackers", "EQUITIES", "equity"],
  ["vanguard", "EQ.STOCK", "equity"],
  ["vanguard", "EQ.REIT", "real_estate"],
  ["vanguard", "EQ.ETF", "fund"],
  ["vanguard", "MF.MF", "fund"],
  ["vanguard", "FI.CORP", "fixed_income"],
  ["vanguard", "MM.TBILL", "cash"],
  ["vanguard", "CT.CASH", "cash"],
  ["vanguard", "CRNY", "cash"],
  ["vanguard", "DE.FUT", "derivative"],
  ["vanguard", "eq.stock", "equity"],
  ["vanguard", "XX.YY", "other"],
  ["amundi", "EQUITY_ORDINARY", "equity"],
  ["amundi", "BOND_GOV", "fixed_income"],
  ["amundi", "FIXED_INCOME", "fixed_income"],
  ["amundi", "CASH", "cash"],
  ["amundi", "CURRENCY_FORWARD", "cash"],
  ["amundi", "FUTURE_INDEX", "derivative"],
  ["amundi", "SWAP", "derivative"],
  ["amundi", "FORWARD", "derivative"],
  ["amundi", "OPTION_CALL", "derivative"],
  ["amundi", "DERIVATIVE", "derivative"],
  ["amundi", "FUND", "fund"],
  ["amundi", "ETF", "fund"],
  ["amundi", "equity_preferred", "equity"],
  ["amundi", "WARRANT", "other"],
  ["spdr", "Equity", "other"],
];

test("asset class mapping", () => {
  for (const [issuer, raw, expected] of CASES) {
    assert.equal(normalizeAssetClass(issuer, raw), expected, `${issuer} ${raw}`);
    assert.ok(ASSET_CLASSES.includes(expected as never));
  }
  for (const raw of [null, undefined, "", "  ", "-"]) assert.equal(normalizeAssetClass("ishares", raw), null);
});

test("every recorded holding has a class from the vocabulary; SPDR and Invesco give none", async () => {
  const client = new HoldingsClient({ transport: recordedTransport(), cacheDir: null });
  for (const isin of RECORDED_ISINS) {
    for (const h of (await client.get(isin)).holdings) {
      if (h.asset_class_raw === null) assert.equal(h.asset_class, null);
      else assert.ok(ASSET_CLASSES.includes(h.asset_class as never));
    }
  }
  for (const isin of ["IE00B5M1WJ87", "IE000716YHJ7"]) {
    const holdings = (await client.get(isin)).holdings;
    assert.ok(holdings.every((h) => h.asset_class === null && h.asset_class_raw === null));
  }
});
