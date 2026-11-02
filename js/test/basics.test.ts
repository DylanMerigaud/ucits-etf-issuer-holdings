import assert from "node:assert/strict";
import { test } from "node:test";
import {
  FundNotFound,
  HoldingsError,
  InvalidISIN,
  IssuerUnavailable,
  NotListed,
  TransportError,
  lookThrough,
  nameOf,
  normalizeIsin,
  toIso2,
  topHoldings,
  totalWeight,
  weightsBy,
  type Fund,
  type WeightKey,
} from "../dist/index.js";
import { pyFloat, pyG, pyRound } from "../dist/pyish.js";
import { unescapeHtml } from "../dist/htmlEntities.js";

test("valid ISINs pass", () => {
  for (const isin of ["IE00B4L5Y983", "IE00BK5BQT80", "LU0274211480", "US0378331005", "IE000716YHJ7"]) {
    assert.equal(normalizeIsin(isin), isin);
  }
});

test("ISIN is stripped and upper-cased", () => {
  assert.equal(normalizeIsin("  ie00b4l5y983\n"), "IE00B4L5Y983");
});

test("invalid ISINs throw InvalidISIN", () => {
  for (const bad of ["", "IE00B4L5Y98", "IE00B4L5Y9833", "1E00B4L5Y983", "IE00B4L5Y984", "IE00B4L5Y98X", "IE00B4L5-983"]) {
    assert.throws(() => normalizeIsin(bad), InvalidISIN, bad);
  }
  assert.throws(() => normalizeIsin(null as unknown as string), InvalidISIN);
  assert.throws(() => normalizeIsin("nope"), { message: "not an ISIN: 'nope'" });
  assert.throws(() => normalizeIsin("IE00B4L5Y984"), { message: "bad check digit: 'IE00B4L5Y984'" });
});

test("countries: codes, names, unknowns", () => {
  assert.equal(toIso2("US"), "US");
  assert.equal(toIso2("de"), "DE");
  assert.equal(toIso2("United States"), "US");
  assert.equal(toIso2("  germany "), "DE");
  assert.equal(toIso2("Korea (South)"), "KR");
  assert.equal(toIso2("Atlantis"), null);
  assert.equal(toIso2(""), null);
  assert.equal(toIso2(null), null);
  assert.equal(toIso2("ZZ"), null);
  assert.equal(nameOf("US"), "United States");
  assert.equal(nameOf("fr"), "France");
  assert.equal(nameOf("ZZ"), null);
  assert.equal(nameOf(null), null);
});

test("errors: messages and hierarchy", () => {
  const nl = new NotListed("ishares", "IE00B4L5Y983");
  assert.equal(nl.message, "ishares: IE00B4L5Y983: not listed");
  assert.ok(nl instanceof HoldingsError);
  const iu = new IssuerUnavailable("spdr", "down");
  assert.equal(iu.message, "spdr: down");
  const fnf = new FundNotFound("IE00B4L5Y983", { ishares: "a", spdr: "b" });
  assert.equal(fnf.message, "IE00B4L5Y983: no issuer returned holdings (ishares: a; spdr: b)");
  assert.deepEqual(fnf.reasons, { ishares: "a", spdr: "b" });
  assert.ok(new TransportError("x") instanceof HoldingsError);
  assert.equal(new InvalidISIN("x").name, "InvalidISIN");
});

function makeFund(): Fund {
  const h = (name: string, weight: number, country: string | null, sector: string | null = null) => ({
    name, weight, isin: null, ticker: null, country, country_name: null, sector, currency: null, asset_class: null, asset_class_raw: null,
  });
  return {
    isin: "IE00B4L5Y983", issuer: "ishares", fund_name: "Test", as_of: "2026-10-30", currency: "USD",
    source_url: "u", fetched_at: "2026-11-02T10:00:00Z", stale: false,
    holdings: [h("A", 50, "US", "Tech"), h("B", 30, "JP", "Tech"), h("C", 15, "US"), h("D", 5, null)],
  };
}

test("models: total, weightsBy, top", () => {
  const fund = makeFund();
  assert.ok(Math.abs(totalWeight(fund) - 100) < 1e-9);
  assert.deepEqual(weightsBy(fund, "country"), [["US", 65], ["JP", 30], [null, 5]]);
  assert.deepEqual(weightsBy(fund, "sector"), [["Tech", 80], [null, 20]]);
  assert.throws(() => weightsBy(fund, "name" as WeightKey), RangeError);
  assert.deepEqual(topHoldings(fund, 2).map((x) => x.name), ["A", "B"]);
});

test("lookThrough spreads positions over holdings", () => {
  const a = makeFund();
  a.holdings = a.holdings.slice(0, 2).map((x, i) => ({ ...x, weight: i === 0 ? 60 : 40 }));
  const b = makeFund();
  b.isin = "IE00BK5BQT80";
  b.holdings = [
    { ...b.holdings[0]!, name: "C", weight: 50, country: "US" },
    { ...b.holdings[0]!, name: "D", weight: 25, country: null },
  ];
  const result = lookThrough(
    { IE00B4L5Y983: 7000, ie00bk5bqt80: 3000 },
    { IE00B4L5Y983: a, IE00BK5BQT80: b },
    "country",
  );
  assert.deepEqual(result, [["US", 5700], ["JP", 2800], [null, 750]]);
  assert.throws(() => lookThrough({ IE00B4L5Y983: 1 }, {}, "country"), /no fund given/);
  assert.throws(() => lookThrough({}, {}, "name"), RangeError);
});

test("python-like number formatting", () => {
  assert.equal(pyFloat(5), "5.0");
  assert.equal(pyFloat(5.6239), "5.6239");
  assert.equal(pyFloat(0.0001), "0.0001");
  assert.equal(pyFloat(0.00001), "1e-05");
  assert.equal(pyFloat(1e16), "1e+16");
  assert.equal(pyFloat(123456.5), "123456.5");
  assert.equal(pyG(65), "65");
  assert.equal(pyG(5.6239), "5.6239");
  assert.equal(pyG(1234567), "1.23457e+06");
  assert.equal(pyG(0.5), "0.5");
  assert.equal(pyRound(5.60273305739550812, 10), 5.6027330574);
});

test("html entities", () => {
  assert.equal(unescapeHtml("ELI LILLY &amp; CO"), "ELI LILLY & CO");
  assert.equal(unescapeHtml("A &#38; B &#x26; C &eacute; &lt;x&gt; &ampfoo"), "A & B & C é <x> &foo");
  assert.equal(unescapeHtml("no entity & here &unknown;"), "no entity & here &unknown;");
});
