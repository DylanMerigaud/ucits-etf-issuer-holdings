// A changed answer shape is IssuerUnavailable (or a dropped line), never a raw JavaScript error.
// Each test replays the recorded answer of a fund with one part of it altered in memory.
import assert from "node:assert/strict";
import { test } from "node:test";
import { FundNotFound, HoldingsClient, IssuerUnavailable } from "../dist/index.js";
import { HttpResponse } from "../dist/http.js";
import { ISSUERS, type Issuer } from "../dist/issuers/index.js";
import type { Fund } from "../dist/models.js";
import { recordedTransport } from "../dist/testing.js";
import { readSheet, XlsxError } from "../dist/xlsx.js";
import { RewritingTransport, withJson } from "./stubs.js";
import { build } from "./xlsxbuild.js";

type Any = any;
type Mutate = (data: Any) => void;

function jsonRewriter(match: (url: string, data: Any) => boolean, mutate: Mutate): RewritingTransport {
  return new RewritingTransport((_method, url, answer) => {
    if (answer.status !== 200 || !answer.contentType.includes("json")) return answer;
    const data = answer.json() as Any;
    if (!match(url, data)) return answer;
    mutate(data);
    return withJson(answer, data);
  });
}

const fetchFund = (issuer: string, isin: string, transport: RewritingTransport): Promise<Fund> =>
  ISSUERS[issuer]!.fetch(isin, transport);

const unavailable = (issuer: string, isin: string, transport: RewritingTransport, message?: RegExp) =>
  assert.rejects(fetchFund(issuer, isin, transport), (e: unknown) => {
    assert.ok(e instanceof IssuerUnavailable, `got ${String(e)}`);
    if (message) assert.match(e.reason, message);
    return true;
  });

// ---------------------------------------------------------------- Vanguard

const VANGUARD = "IE00BK5BQT80";
const isFunds = (url: string, data: Any) => url.includes("graphql") && !("borHoldings" in (data.data ?? {}));
const isHoldings = (url: string, data: Any) => url.includes("graphql") && "borHoldings" in (data.data ?? {});
const setItems = (value: unknown): Mutate => (data) => {
  data.data.borHoldings[0].holdings.items = value;
};

test("vanguard: items null or not a list, borHoldings empty", async () => {
  await unavailable("vanguard", VANGUARD, jsonRewriter(isHoldings, setItems(null)));
  await unavailable("vanguard", VANGUARD, jsonRewriter(isHoldings, setItems({ a: 1 })));
  await unavailable("vanguard", VANGUARD, jsonRewriter(isHoldings, (d) => (d.data.borHoldings = [])));
});

test("vanguard: profile null keeps the holdings", async () => {
  const fund = await fetchFund("vanguard", VANGUARD, jsonRewriter(isHoldings, (d) => (d.data.funds[0].profile = null)));
  assert.deepEqual([fund.fund_name, fund.currency, fund.holdings.length], [null, null, 25]);
});

test("vanguard: portId missing or null is unavailable, never sent as a string", async () => {
  await unavailable("vanguard", VANGUARD, jsonRewriter(isFunds, (d) => delete d.data.funds[0].portId), /portId/);
  await unavailable("vanguard", VANGUARD, jsonRewriter(isFunds, (d) => (d.data.funds[0].portId = null)), /portId/);
});

test("vanguard: a non-object fund or identifier is skipped", async () => {
  const fund = await fetchFund("vanguard", VANGUARD, jsonRewriter(isFunds, (d) => {
    const funds = d.data.funds;
    funds[0].profile.identifiers.unshift("IE00BK5BQT80", null);
    funds.unshift(7, null);
  }));
  assert.equal(fund.holdings.length, 25);
});

test("vanguard: funds null is unavailable", async () => {
  await unavailable("vanguard", VANGUARD, jsonRewriter(isFunds, (d) => (d.data.funds = null)));
});

test("vanguard: portIds not a string is unavailable", async () => {
  const transport = new RewritingTransport((method, url, answer) => {
    if (method !== "GET") return answer;
    const body = answer.text.replace('"9679,9505,9104"', "null");
    return new HttpResponse(200, new TextEncoder().encode(body), answer.contentType, url);
  });
  await unavailable("vanguard", VANGUARD, transport);
});

test("vanguard: a non-object item is skipped", async () => {
  const fund = await fetchFund("vanguard", VANGUARD, jsonRewriter(isHoldings, (d) => d.data.borHoldings[0].holdings.items.unshift(null)));
  assert.equal(fund.holdings.length, 25);
});

// ---------------------------------------------------------------- iShares

const ISHARES = "IE00B4L5Y983";
const isISharesHoldings = (url: string) => url.includes("get-product-data");
const pointsOf = (d: Any) => d.componentsByNameMap.holdings.containersByNameMap.all.dataPointsByNameMap;
const isScreener = (url: string) => url.includes("screener");
const forEntry = (mutate: (entry: Any) => void): Mutate => (data) => {
  for (const value of Object.values(data) as Any[]) {
    if (value && typeof value === "object" && value.isin === ISHARES) mutate(value);
  }
};

test("ishares: points not an object, names column not an object", async () => {
  await unavailable("ishares", ISHARES, jsonRewriter(isISharesHoldings, (d) => {
    d.componentsByNameMap.holdings.containersByNameMap.all.dataPointsByNameMap = ["x"];
  }));
  await unavailable("ishares", ISHARES, jsonRewriter(isISharesHoldings, (d) => (pointsOf(d).issueName = "x")));
});

test("ishares: a null column reads as null, a short column is padded", async () => {
  const fund = await fetchFund("ishares", ISHARES, jsonRewriter(isISharesHoldings, (d) => {
    pointsOf(d).isin = null;
    pointsOf(d).ticker = { value: null };
  }));
  assert.equal(fund.holdings.length, 20);
  assert.ok(fund.holdings.every((h) => h.isin === null && h.ticker === null));
  const short = await fetchFund("ishares", ISHARES, jsonRewriter(isISharesHoldings, (d) => {
    pointsOf(d).isin.value = pointsOf(d).isin.value.slice(0, 1);
  }));
  assert.equal(short.holdings[0]!.isin, "US0378331005");
  assert.equal(short.holdings[1]!.isin, null);
});

test("ishares: asOfDate not an object gives no as_of", async () => {
  const fund = await fetchFund("ishares", ISHARES, jsonRewriter(isISharesHoldings, (d) => (pointsOf(d).asOfDate = 20261030)));
  assert.equal(fund.as_of, null);
});

test("ishares: portfolioId null is unavailable", async () => {
  await unavailable("ishares", ISHARES, jsonRewriter(isScreener, forEntry((e) => (e.portfolioId = null))));
});

test("ishares: fund name not a string, blank currency", async () => {
  const fund = await fetchFund("ishares", ISHARES, jsonRewriter(isScreener, forEntry((e) => {
    e.fundName = 42;
    e.seriesBaseCurrencyCode = "  ";
  })));
  assert.deepEqual([fund.fund_name, fund.currency], [null, null]);
});

// ---------------------------------------------------------------- SPDR

const SPDR = "IE00B5M1WJ87";
const isFinder = (url: string) => url.includes("fundfinder");

test("spdr: datas null, funds not an object", async () => {
  await unavailable("spdr", SPDR, jsonRewriter(isFinder, (d) => (d.data.funds.etfs.datas = null)));
  await unavailable("spdr", SPDR, jsonRewriter(isFinder, (d) => (d.data.funds = "x")));
});

test("spdr: null entries are skipped", async () => {
  const fund = await fetchFund("spdr", SPDR, jsonRewriter(isFinder, (d) => {
    const datas = d.data.funds.etfs.datas;
    for (const f of datas) f.documentPdf.unshift({ docs: [null, { path: 5 }] }, { docs: null }, null);
    datas.unshift({ fundTicker: 3, documentPdf: "x" }, null);
  }));
  assert.equal(fund.holdings.length, 40);
});

// ---------------------------------------------------------------- Amundi

const AMUNDI = "IE000BI8OT95";
const isAmundi = (url: string) => url.includes("amundietf");

test("amundi: characteristics and currencies not objects", async () => {
  const fund = await fetchFund("amundi", AMUNDI, jsonRewriter(isAmundi, (d) => {
    d.products[0].characteristics = "x";
    d.products[0].currencies = ["USD"];
  }));
  assert.deepEqual([fund.fund_name, fund.currency, fund.holdings.length], [null, null, 20]);
});

test("amundi: fund name not a non-empty string", async () => {
  const fund = await fetchFund("amundi", AMUNDI, jsonRewriter(isAmundi, (d) => {
    d.products[0].characteristics.SHARE_MARKETING_NAME = "";
    d.products[0].currencies.BASE_CURRENCY = 5;
  }));
  assert.deepEqual([fund.fund_name, fund.currency], [null, null]);
});

test("amundi: compositionCharacteristics not an object drops the line", async () => {
  const fund = await fetchFund("amundi", AMUNDI, jsonRewriter(isAmundi, (d) => {
    const rows = d.products[0].composition.compositionData;
    rows[0].compositionCharacteristics = "x";
    rows.unshift(null);
  }));
  assert.equal(fund.holdings.length, 19);
});

test("amundi: rows null, composition not an object, product null", async () => {
  await unavailable("amundi", AMUNDI, jsonRewriter(isAmundi, (d) => (d.products[0].composition.compositionData = null)));
  await unavailable("amundi", AMUNDI, jsonRewriter(isAmundi, (d) => (d.products[0].composition = [])));
  await unavailable("amundi", AMUNDI, jsonRewriter(isAmundi, (d) => (d.products[0] = null)));
});

test("amundi: a datetime is cut to its date", async () => {
  const fund = await fetchFund("amundi", AMUNDI, jsonRewriter(isAmundi, (d) => {
    for (const row of d.products[0].composition.compositionData) {
      row.compositionCharacteristics.date = "2026-10-29T00:00:00.000Z";
    }
  }));
  assert.equal(fund.as_of, "2026-10-29");
});

// ---------------------------------------------------------------- Invesco

const INVESCO = "IE000716YHJ7";
const isInvesco = (url: string) => url.includes("invesco");

test("invesco: a null row is skipped", async () => {
  const fund = await fetchFund("invesco", INVESCO, jsonRewriter(isInvesco, (d) => d.holdings.unshift("x", null)));
  assert.equal(fund.holdings.length, 20);
});

const AS_OF_CASES: Array<[unknown, string | null]> = [
  ["2026-10-30T00:00:00", "2026-10-30"],
  ["2026-10-30 12:00", "2026-10-30"],
  ["30/10/2026", null],
  ["2026-10-30x", null],
  [20261030, null],
  [null, null],
];

test("invesco: as_of only when it is a date", async () => {
  for (const [given, asOf] of AS_OF_CASES) {
    const fund = await fetchFund("invesco", INVESCO, jsonRewriter(isInvesco, (d) => (d.effectiveDate = given)));
    assert.equal(fund.as_of, asOf, String(given));
  }
});

// ---------------------------------------------------------------- xlsx

test("xlsx: a shared string index out of range is an XlsxError", () => {
  for (const index of ["1", "-1", "x"]) {
    const sheet = `<row r="1"><c r="A1" t="s"><v>${index}</v></c></row>`;
    assert.throws(() => readSheet(build(sheet, "<si><t>a</t></si>")), XlsxError);
  }
});

test("xlsx: a corrupt deflate stream and a truncated file are XlsxError", () => {
  const data = Buffer.from(build("<row/>".repeat(200), undefined, true));
  const name = "xl/worksheets/sheet7.xml";
  const start = data.indexOf(name) + name.length;
  for (let i = start; i < start + 20; i++) data[i] = data[i]! ^ 0xff;
  assert.throws(() => readSheet(data), XlsxError);
  const whole = build("");
  assert.throws(() => readSheet(whole.slice(0, whole.length / 2)), XlsxError);
});

// ---------------------------------------------------------------- client

test("an unexpected error in one issuer does not stop the lookup", async () => {
  const table = ISSUERS as Record<string, Issuer>;
  const original = table["ishares"]!;
  table["ishares"] = {
    name: "ishares",
    fetch: async () => {
      throw new TypeError("Cannot read properties of null (reading 'portfolioId')");
    },
  };
  try {
    const client = new HoldingsClient({ transport: recordedTransport(), cacheDir: null });
    assert.equal((await client.get("IE000716YHJ7")).issuer, "invesco");
    await assert.rejects(client.get("US0378331005"), (e: FundNotFound) => {
      assert.equal(e.reasons["ishares"], "unexpected answer: TypeError: Cannot read properties of null (reading 'portfolioId')");
      return true;
    });
  } finally {
    table["ishares"] = original;
  }
});

test("toString and other Object members are unknown issuers", async () => {
  const client = new HoldingsClient({ transport: recordedTransport(), cacheDir: null });
  for (const name of ["toString", "constructor", "__proto__", "hasOwnProperty"]) {
    await assert.rejects(client.get("IE00B4L5Y983", { issuer: name }), /unknown issuer/);
    assert.throws(() => new HoldingsClient({ issuers: [name] }), /unknown issuer\(s\)/);
  }
});
