import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { HoldingsClient, VERSION } from "../dist/index.js";
import { RECORDED_ISINS, recordedTransport } from "../dist/testing.js";

const root = fileURLToPath(new URL("../../", import.meta.url));
const snapshotFile = new URL("../test/fixtures/python-funds.json", import.meta.url);

type Dump = Record<string, Record<string, unknown>>;

async function tsFunds(): Promise<Dump> {
  const client = new HoldingsClient({ transport: recordedTransport(), cacheDir: null });
  const out: Dump = {};
  for (const isin of RECORDED_ISINS) {
    const fund = await client.get(isin);
    const copy = JSON.parse(JSON.stringify(fund)) as Record<string, unknown>;
    assert.match(String(copy["fetched_at"]), /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
    delete copy["fetched_at"];
    out[isin] = copy;
  }
  return out;
}

function compare(python: Dump, ts: Dump): void {
  assert.deepEqual(Object.keys(ts), Object.keys(python));
  for (const isin of Object.keys(python)) {
    assert.deepEqual(Object.keys(ts[isin]!), Object.keys(python[isin]!), `${isin}: key order`);
    assert.deepEqual(ts[isin], python[isin], isin);
  }
}

test("TS funds equal the committed Python snapshot (apart from fetched_at)", async () => {
  const snapshot = JSON.parse(readFileSync(snapshotFile, "utf8")) as Dump;
  assert.equal(Object.keys(snapshot).length, RECORDED_ISINS.length);
  compare(snapshot, await tsFunds());
});

function uvAvailable(): boolean {
  try {
    execFileSync(process.env["UV"] ?? "uv", ["--version"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

const uv = uvAvailable();
test("TS funds equal a live run of the Python package", { skip: uv ? false : "uv is not installed: the committed snapshot test covers parity" }, async () => {
  const script = `
import json
from ucits_etf_issuer_holdings import HoldingsClient
from ucits_etf_issuer_holdings.testing import RECORDED_ISINS, recorded_transport
client = HoldingsClient(transport=recorded_transport(), cache_dir=None)
print(json.dumps({isin: client.get(isin).to_dict() for isin in RECORDED_ISINS}))
`;
  const text = execFileSync(process.env["UV"] ?? "uv", ["run", "python", "-c", script], { cwd: root, encoding: "utf8", maxBuffer: 64 << 20 });
  const python = JSON.parse(text) as Dump;
  for (const fund of Object.values(python)) delete fund["fetched_at"];
  compare(python, await tsFunds());
});

test("package version matches package.json", () => {
  const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8")) as { version: string };
  assert.equal(VERSION, pkg.version);
});
