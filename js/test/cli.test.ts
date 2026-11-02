import assert from "node:assert/strict";
import { test } from "node:test";
import { main } from "../dist/cliMain.js";
import { recordedTransport } from "../dist/testing.js";

async function run(args: string[]): Promise<{ code: number; out: string; err: string }> {
  let out = "";
  let err = "";
  const code = await main(args, { transport: recordedTransport(), stdout: (t) => (out += t), stderr: (t) => (err += t) });
  return { code, out, err };
}

test("json by default", async () => {
  const { code, out } = await run(["IE000716YHJ7", "--no-cache"]);
  assert.equal(code, 0);
  const data = JSON.parse(out);
  assert.equal(data.isin, "IE000716YHJ7");
  assert.equal(data.issuer, "invesco");
  assert.equal(data.holdings.length, 20);
});

test("csv", async () => {
  const { code, out } = await run(["IE000716YHJ7", "--format", "csv", "--issuer", "invesco", "--no-cache"]);
  assert.equal(code, 0);
  const lines = out.trimEnd().split("\n");
  assert.equal(lines.length, 21);
  assert.equal(lines[0], "name,weight,isin,ticker,country,country_name,sector,currency,asset_class,asset_class_raw");
  assert.ok(lines[1]!.startsWith("APPLE INC USD0.00001,4.74,US0378331005"));
});

test("table", async () => {
  const { code, out } = await run(["IE00B4L5Y983", "--format", "table", "--no-cache"]);
  assert.equal(code, 0);
  assert.ok(out.includes("iShares Core MSCI World UCITS ETF (ishares, as of 2026-10-30)"));
  assert.ok(out.includes("APPLE") && out.includes("5.6239"));
});

test("--by country as json, table and csv", async () => {
  const json = JSON.parse((await run(["IE00B4L5Y983", "--by", "country", "--no-cache"])).out);
  assert.deepEqual(Object.keys(json[0]).sort(), ["country", "weight"]);
  assert.equal(json[0].country, "US");
  const table = await run(["IE00B4L5Y983", "--by", "sector", "--format", "table", "--no-cache"]);
  assert.ok(table.out.toLowerCase().includes("sector"));
  const csv = await run(["IE00B4L5Y983", "--by", "sector", "--format", "csv", "--no-cache"]);
  assert.equal(csv.out.split("\n")[0], "sector,weight");
});

test("invalid ISIN exits 2, unknown fund exits 1", async () => {
  const bad = await run(["nope", "--no-cache"]);
  assert.equal(bad.code, 2);
  assert.equal(bad.out, "");
  assert.ok(bad.err.includes("not an ISIN"));
  const missing = await run(["US0378331005", "--no-cache"]);
  assert.equal(missing.code, 1);
  assert.ok(missing.err.includes("ishares"));
});

test("bad options exit 2; version", async () => {
  assert.equal((await run(["IE00B4L5Y983", "--format", "xml"])).code, 2);
  assert.equal((await run([])).code, 2);
  assert.equal((await run(["--bogus", "x"])).code, 2);
  assert.equal((await run(["--version"])).out, "ucits-holdings 0.1.0\n");
});
