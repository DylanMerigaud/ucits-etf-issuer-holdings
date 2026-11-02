import assert from "node:assert/strict";
import { test } from "node:test";
import { IssuerUnavailable, NotListed, TransportError } from "../dist/errors.js";
import { AmundiIssuer } from "../dist/issuers/amundi.js";
import { InvescoIssuer } from "../dist/issuers/invesco.js";
import { ISharesIssuer } from "../dist/issuers/ishares.js";
import { SpdrIssuer, slugOf } from "../dist/issuers/spdr.js";
import { VanguardIssuer } from "../dist/issuers/vanguard.js";
import { XtrackersIssuer } from "../dist/issuers/xtrackers.js";
import { RecordedTransport, recordedTransport } from "../dist/testing.js";
import { RewritingTransport, StaticTransport, reply, withJson } from "./stubs.js";
import { NS, REL, build, zip } from "./xlsxbuild.js";
import { readSheet } from "../dist/xlsx.js";

const near = (a: number, b: number) => assert.ok(Math.abs(a - b) < 1e-9, `${a} vs ${b}`);
const json = (data: unknown) => reply(200, JSON.stringify(data), "application/json");

// ---------------------------------------------------------------- iShares

test("ishares: equity fund", async () => {
  const fund = await new ISharesIssuer().fetch("IE00B4L5Y983", recordedTransport());
  assert.equal(fund.issuer, "ishares");
  assert.equal(fund.fund_name, "iShares Core MSCI World UCITS ETF");
  assert.equal(fund.as_of, "2026-10-30");
  assert.equal(fund.currency, "USD");
  assert.equal(fund.stale, false);
  assert.equal(fund.holdings.length, 20);
  const first = fund.holdings[0]!;
  assert.deepEqual([first.name, first.weight, first.isin], ["APPLE", 5.6239, "US0378331005"]);
  assert.deepEqual([first.country, first.country_name], ["US", "United States"]);
  assert.equal(first.ticker, "AAPL");
  assert.ok(first.sector && first.currency === "USD" && first.asset_class === "Equity");
  assert.equal(fund.holdings[17]!.country, "NL");
  assert.ok(fund.source_url.includes("portfolioId=251882"));
});

test("ishares: bond fund", async () => {
  const fund = await new ISharesIssuer().fetch("IE00B3F81409", recordedTransport());
  assert.equal(fund.fund_name, "iShares Core Global Aggregate Bond UCITS ETF");
  assert.equal(fund.holdings.length, 12);
  assert.equal(fund.holdings[0]!.name, "BLK ICS USD LEAF AGENCY DIST");
  assert.equal(fund.holdings[0]!.weight, 1.9646);
});

test("ishares: not listed", async () => {
  await assert.rejects(new ISharesIssuer().fetch("IE00BK5BQT80", recordedTransport()), (e: NotListed) => {
    assert.ok(e instanceof NotListed);
    assert.equal(e.issuer, "ishares");
    return true;
  });
});

test("ishares: unwraps raw/display values", async () => {
  const t = new RewritingTransport((_m, url, answer) => {
    if (!url.includes("product-screener")) return answer;
    const data = answer.json() as Record<string, Record<string, unknown>>;
    data["251882"]!["isin"] = { r: "IE00B4L5Y983", d: "IE00B4L5Y983" };
    return withJson(answer, data);
  });
  assert.equal((await new ISharesIssuer().fetch("IE00B4L5Y983", t)).holdings.length, 20);
});

test("ishares: missing path is unavailable", async () => {
  const t = new RewritingTransport((_m, url, a) => (url.includes("get-product-data") ? withJson(a, { componentsByNameMap: {} }) : a));
  await assert.rejects(new ISharesIssuer().fetch("IE00B4L5Y983", t), IssuerUnavailable);
});

function points(data: unknown): Record<string, { value: unknown[] }> {
  const d = data as { componentsByNameMap: { holdings: { containersByNameMap: { all: { dataPointsByNameMap: Record<string, { value: unknown[] }> } } } } };
  return d.componentsByNameMap.holdings.containersByNameMap.all.dataPointsByNameMap;
}

test("ishares: rows without weight are dropped", async () => {
  const t = new RewritingTransport((_m, url, a) => {
    if (!url.includes("get-product-data")) return a;
    const data = a.json();
    points(data)["holdingPercent"]!.value[0] = null;
    return withJson(a, data);
  });
  const fund = await new ISharesIssuer().fetch("IE00B4L5Y983", t);
  assert.equal(fund.holdings.length, 19);
  assert.equal(fund.holdings[0]!.name, "NVIDIA");
});

test("ishares: missing column reads as null", async () => {
  const t = new RewritingTransport((_m, url, a) => {
    if (!url.includes("get-product-data")) return a;
    const data = a.json();
    delete points(data)["sectorName"];
    return withJson(a, data);
  });
  assert.equal((await new ISharesIssuer().fetch("IE00B4L5Y983", t)).holdings[0]!.sector, null);
});

test("ishares: network and HTTP errors are unavailable", async () => {
  await assert.rejects(new ISharesIssuer().fetch("IE00B4L5Y983", new StaticTransport(new TransportError("down"))), IssuerUnavailable);
  await assert.rejects(new ISharesIssuer().fetch("IE00B4L5Y983", new StaticTransport(reply(503, ""))), IssuerUnavailable);
  await assert.rejects(new ISharesIssuer().fetch("IE00B4L5Y983", new StaticTransport(reply(200, "<html>"))), IssuerUnavailable);
});

// ---------------------------------------------------------------- Vanguard

test("vanguard: fund with two pages", async () => {
  const t = recordedTransport();
  const fund = await new VanguardIssuer().fetch("IE00BK5BQT80", t);
  assert.equal(fund.issuer, "vanguard");
  assert.equal(fund.fund_name, "Vanguard FTSE All-World UCITS ETF (USD) Accumulating");
  assert.equal(fund.currency, "USD");
  assert.equal(fund.as_of, "2026-09-30");
  assert.equal(fund.holdings.length, 25);
  const first = fund.holdings[0]!;
  assert.deepEqual([first.name, first.weight, first.ticker], ["NVIDIA Corp", 5.0056, "NVDA"]);
  assert.deepEqual([first.country, first.country_name], ["US", "United States"]);
  assert.equal(first.sector, "Information Technology");
  assert.equal(first.asset_class, "EQ.STOCK");
  assert.equal(first.isin, null);
  assert.equal(t.requests.filter(([m]) => m === "POST").length, 3);
});

test("vanguard: not listed", async () => {
  await assert.rejects(new VanguardIssuer().fetch("IE00B4L5Y983", recordedTransport()), NotListed);
});

test("vanguard: graphql errors are unavailable", async () => {
  const t = new RewritingTransport((_m, _u, a) => {
    if (a.contentType !== "application/json") return a;
    const data = a.json() as { data?: { borHoldings?: unknown } };
    return data?.data?.borHoldings ? withJson(a, { errors: [{ message: "boom" }] }) : a;
  });
  await assert.rejects(new VanguardIssuer().fetch("IE00BK5BQT80", t), IssuerUnavailable);
});

test("vanguard: missing port ids is unavailable", async () => {
  const t = new RewritingTransport((m, url, a) => (m === "GET" ? reply(200, "<html>nothing here</html>", "text/html") : a));
  await assert.rejects(new VanguardIssuer().fetch("IE00BK5BQT80", t), IssuerUnavailable);
});

test("vanguard: lastItemKey goes back as the object received, page guard stops endless paging", async () => {
  const page1 = (await recordedTransport().request("POST", "https://www.de.vanguard/gpx/graphql", {
    json: { operationName: "FundsHoldingsQuery", variables: { portIds: ["9679"], lastItemKey: null } },
  })).json() as { data: { borHoldings: Array<{ holdings: { lastItemKey: unknown } }> } };
  const key = page1.data.borHoldings[0]!.holdings.lastItemKey;
  const t = new RewritingTransport((_m, _u, a) => {
    if (a.contentType !== "application/json") return a;
    const data = a.json() as { data: { borHoldings?: Array<{ holdings: { lastItemKey: unknown } }> } };
    if (data.data.borHoldings) {
      data.data.borHoldings[0]!.holdings.lastItemKey = key;
      return withJson(a, data);
    }
    return a;
  });
  const seen: unknown[] = [];
  const inner = t.request.bind(t);
  t.request = async (method, url, options) => {
    seen.push((options?.json as { variables?: { lastItemKey?: unknown } } | undefined)?.variables?.lastItemKey);
    return inner(method, url, options);
  };
  await assert.rejects(new VanguardIssuer().fetch("IE00BK5BQT80", t), /20 pages/);
  assert.equal(t.calls, 2 + 20);
  assert.deepEqual(seen.slice(3, 5), [key, key]);
});

// ---------------------------------------------------------------- Xtrackers

test("xtrackers: fund", async () => {
  const fund = await new XtrackersIssuer().fetch("LU0274211480", recordedTransport());
  assert.equal(fund.issuer, "xtrackers");
  assert.equal(fund.as_of, "2026-11-02");
  assert.equal(fund.holdings.length, 43);
  const first = fund.holdings[0]!;
  assert.equal(first.name, "SAP");
  near(first.weight, 11.76506915);
  assert.equal(first.isin, "DE0007164600");
  assert.deepEqual([first.country, first.country_name], ["DE", "Germany"]);
  assert.equal(first.currency, "EUR");
  assert.equal(first.sector, "Technology");
  assert.equal(first.asset_class, "Equities");
  assert.equal(fund.holdings[4]!.name, "AIRBUS");
  assert.equal(fund.holdings[4]!.country, "FR");
});

test("xtrackers: cash lines have no isin or country", async () => {
  const fund = await new XtrackersIssuer().fetch("LU0274211480", recordedTransport());
  const euro = fund.holdings.find((h) => h.name === "EURO CURRENCY")!;
  assert.equal(euro.isin, null);
  assert.equal(euro.country, null);
  assert.equal(euro.asset_class, "Cash");
});

test("xtrackers: not listed when the answer is not an xlsx", async () => {
  await assert.rejects(new XtrackersIssuer().fetch("IE00B4L5Y983", recordedTransport()), NotListed);
  await assert.rejects(new XtrackersIssuer().fetch("IE00B4L5Y983", new StaticTransport(reply(500, "<html>error</html>"))), NotListed);
});

test("xtrackers: network error is unavailable", async () => {
  await assert.rejects(new XtrackersIssuer().fetch("LU0274211480", new StaticTransport(new TransportError("down"))), IssuerUnavailable);
});

test("xtrackers: xlsx without header is unavailable", async () => {
  const t = new RewritingTransport((_m, _u, a) => {
    // rebuild the workbook with the header word changed, as a stored zip
    const [, rows] = readSheet(a.content);
    const cells = rows
      .map((r, i) => `<row r="${i + 1}">${r.map((c, j) => (c === null ? "" : `<c r="${String.fromCharCode(65 + j)}${i + 1}" t="inlineStr"><is><t>${String(c).replace("Weighting", "Other")}</t></is></c>`)).join("")}</row>`)
      .join("");
    return a.with({ content: build(cells) });
  });
  await assert.rejects(new XtrackersIssuer().fetch("LU0274211480", t), IssuerUnavailable);
});

// ---------------------------------------------------------------- Amundi

test("amundi: core fund", async () => {
  const fund = await new AmundiIssuer().fetch("IE000BI8OT95", recordedTransport());
  assert.equal(fund.issuer, "amundi");
  assert.equal(fund.fund_name, "Amundi Core MSCI World UCITS ETF Acc");
  assert.equal(fund.currency, "USD");
  assert.equal(fund.as_of, "2026-10-29");
  assert.equal(fund.holdings.length, 20);
  const first = fund.holdings[0]!;
  assert.equal(first.name, "APPLE INC");
  near(first.weight, 5.602733057395508);
  assert.equal(first.isin, "US0378331005");
  assert.deepEqual([first.country, first.country_name], ["US", "United States"]);
  assert.equal(first.sector, "Information Technology");
  assert.equal(first.currency, "USD");
  assert.equal(first.asset_class, "EQUITY_ORDINARY");
});

test("amundi: swap fund", async () => {
  const fund = await new AmundiIssuer().fetch("LU1681043599", recordedTransport());
  assert.equal(fund.fund_name, "Amundi MSCI World Swap UCITS ETF EUR Acc");
  assert.equal(fund.currency, "EUR");
  assert.equal(fund.holdings.length, 20);
  assert.equal(fund.holdings[0]!.name, "AIRBUS SE PARIS");
  near(fund.holdings[0]!.weight, 7.792888583439779);
  assert.equal(fund.holdings[0]!.isin, "NL0000235190");
  assert.equal(fund.holdings[0]!.country, "FR");
});

test("amundi: one POST and the right body", async () => {
  const t = recordedTransport();
  await new AmundiIssuer().fetch("IE000BI8OT95", t);
  assert.deepEqual(t.requests, [["POST", "https://www.amundietf.de/mapi/ProductAPI/getProductsData"]]);
});

test("amundi: empty product list is not listed; shape change and network errors", async () => {
  await assert.rejects(new AmundiIssuer().fetch("IE00B4L5Y983", new StaticTransport(json({ products: [] }))), NotListed);
  const t = new RewritingTransport((_m, _u, a) => {
    const data = a.json() as { products: Array<Record<string, unknown>> };
    delete data.products[0]!["composition"];
    return withJson(a, data);
  });
  await assert.rejects(new AmundiIssuer().fetch("IE000BI8OT95", t), IssuerUnavailable);
  // the replay answers 404 "not recorded": an HTTP error, not "not listed"
  await assert.rejects(new AmundiIssuer().fetch("IE00B4L5Y983", new RecordedTransport()), IssuerUnavailable);
  await assert.rejects(new AmundiIssuer().fetch("IE000BI8OT95", new StaticTransport(new TransportError("down"))), IssuerUnavailable);
});

// ---------------------------------------------------------------- SPDR

test("spdr: fund", async () => {
  const fund = await new SpdrIssuer().fetch("IE00B5M1WJ87", recordedTransport());
  assert.equal(fund.issuer, "spdr");
  assert.equal(fund.fund_name, "State Street® SPDR® S&P® Euro Dividend Aristocrats UCITS ETF (Dist)");
  assert.equal(fund.as_of, "2026-10-30");
  assert.equal(fund.holdings.length, 40);
  const first = fund.holdings[0]!;
  assert.equal(first.name, "Teleperformance SE");
  assert.equal(first.weight, 5.71166);
  assert.equal(first.isin, "FR0000051807");
  assert.deepEqual([first.country, first.country_name], ["FR", "France"]);
  assert.equal(first.sector, "Industrials");
  assert.equal(first.currency, "EUR");
  assert.ok(fund.holdings[fund.holdings.length - 1]!.weight > 0);
  assert.ok(fund.source_url.endsWith("holdings-daily-emea-en-spyw-gy.xlsx"));
});

test("spdr: not listed; listed but file missing; not an xlsx", async () => {
  await assert.rejects(new SpdrIssuer().fetch("IE00B4L5Y983", recordedTransport()), NotListed);
  await assert.rejects(new SpdrIssuer().fetch("IE00BFY0GT14", recordedTransport()), IssuerUnavailable);
  const t = new RewritingTransport((_m, url, a) => (url.endsWith(".xlsx") ? reply(200, "<html></html>", "text/html") : a));
  await assert.rejects(new SpdrIssuer().fetch("IE00B5M1WJ87", t), IssuerUnavailable);
});

test("spdr: xlsx without a header row is unavailable", async () => {
  const bytes = zip({
    "xl/workbook.xml": `<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="${REL}"><sheets><sheet name="holdings" r:id="r1"/></sheets></workbook>`,
    "xl/_rels/workbook.xml.rels": `<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="${REL}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>`,
    "xl/worksheets/sheet1.xml": `<worksheet ${NS}><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>nothing</t></is></c></row></sheetData></worksheet>`,
  });
  const t = new RewritingTransport((_m, url, a) => (url.endsWith(".xlsx") ? a.with({ content: bytes }) : a));
  await assert.rejects(new SpdrIssuer().fetch("IE00B5M1WJ87", t), IssuerUnavailable);
});

test("spdr: slug", () => {
  assert.equal(slugOf("SPYW GY"), "spyw-gy");
  assert.equal(slugOf("ZPRV GY^"), "zprv-gy");
});

// ---------------------------------------------------------------- Invesco

test("invesco: fund", async () => {
  const fund = await new InvescoIssuer().fetch("IE000716YHJ7", recordedTransport());
  assert.equal(fund.issuer, "invesco");
  assert.equal(fund.fund_name, null);
  assert.equal(fund.as_of, "2026-10-30");
  assert.equal(fund.holdings.length, 20);
  const first = fund.holdings[0]!;
  assert.deepEqual([first.name, first.weight, first.isin, first.currency], ["APPLE INC USD0.00001", 4.74, "US0378331005", "USD"]);
  assert.ok(first.country === null && first.sector === null);
  assert.ok(!fund.holdings.map((h) => h.name).join(" ").includes("&amp;"));
  assert.ok(fund.holdings.some((h) => h.name === "ELI LILLY & CO NPV"));
});

test("invesco: sends the Origin header and idType", async () => {
  const t = new StaticTransport(reply(200, "{}", "application/json"));
  await assert.rejects(new InvescoIssuer().fetch("IE000716YHJ7", t), NotListed);
  assert.deepEqual(t.requests[0]!.options.headers, { Origin: "https://www.invesco.com" });
  assert.deepEqual(t.requests[0]!.options.params, { idType: "isin" });
});

test("invesco: empty object and 404 are not listed, 406 and odd shapes are unavailable", async () => {
  await assert.rejects(new InvescoIssuer().fetch("IE00B4L5Y983", new StaticTransport(reply(200, "{}"))), NotListed);
  await assert.rejects(new InvescoIssuer().fetch("IE00B4L5Y983", new StaticTransport(reply(404, ""))), NotListed);
  await assert.rejects(new InvescoIssuer().fetch("IE00B4L5Y983", new StaticTransport(reply(406, ""))), IssuerUnavailable);
  await assert.rejects(new InvescoIssuer().fetch("IE00B4L5Y983", new StaticTransport(json({ holdings: { oops: 1 } }))), IssuerUnavailable);
});

