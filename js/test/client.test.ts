import assert from "node:assert/strict";
import { mkdtemp, readdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import {
  CachingTransport,
  FundNotFound,
  HoldingsClient,
  InvalidISIN,
  TransportError,
  getHoldings,
  type RequestOptions,
} from "../dist/index.js";
import { HttpResponse } from "../dist/http.js";
import { RECORDED_ISINS, RecordedTransport, recordedTransport } from "../dist/testing.js";
import { StaticTransport, reply } from "./stubs.js";

const client = (extra = {}) => new HoldingsClient({ transport: recordedTransport(), cacheDir: null, ...extra });
const tmp = () => mkdtemp(join(tmpdir(), "ucits-"));

for (const isin of RECORDED_ISINS) {
  test(`every recorded ISIN answers: ${isin}`, async () => {
    const fund = await client().get(isin);
    assert.equal(fund.isin, isin);
    assert.ok(fund.holdings.length > 0);
    assert.ok(fund.fetched_at.endsWith("Z"));
    assert.match(fund.fetched_at, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
  });
}

test("issuer of each recorded ISIN", async () => {
  const expected = {
    IE00B4L5Y983: "ishares", IE00B3F81409: "ishares", IE00BK5BQT80: "vanguard", LU0274211480: "xtrackers",
    IE000BI8OT95: "amundi", LU1681043599: "amundi", IE00B5M1WJ87: "spdr", IE000716YHJ7: "invesco",
  };
  const c = client();
  for (const [isin, issuer] of Object.entries(expected)) assert.equal((await c.get(isin)).issuer, issuer);
});

test("ISIN is normalised and validated", async () => {
  assert.equal((await client().get(" ie00b4l5y983 ")).isin, "IE00B4L5Y983");
  await assert.rejects(client().get("nope"), InvalidISIN);
});

test("order: ishares, vanguard, spdr, xtrackers", async () => {
  const t = new RecordedTransport();
  await new HoldingsClient({ transport: t, cacheDir: null }).get("LU0274211480");
  const hosts = [...new Set(t.requests.map(([, url]) => url.split("/")[2]))];
  assert.deepEqual(hosts, ["www.ishares.com", "www.de.vanguard", "www.ssga.com", "etf.dws.com"]);
});

test("issuer hint asks only that issuer", async () => {
  const t = new RecordedTransport();
  await new HoldingsClient({ transport: t, cacheDir: null }).get("IE000716YHJ7", { issuer: "invesco" });
  assert.deepEqual([...new Set(t.requests.map(([, url]) => url.split("/")[2]))], ["dng-api.invesco.com"]);
});

test("unknown issuer is refused", async () => {
  await assert.rejects(client().get("IE00B4L5Y983", { issuer: "nobody" }), { message: "unknown issuer: 'nobody'" });
  assert.throws(() => client({ issuers: ["nobody"] }), /unknown issuer\(s\): nobody/);
});

test("issuers restriction", async () => {
  await assert.rejects(client({ issuers: ["invesco"] }).get("IE00B4L5Y983"), (e: FundNotFound) => {
    assert.deepEqual(Object.keys(e.reasons), ["invesco"]);
    return true;
  });
});

test("FundNotFound carries one reason per issuer", async () => {
  await assert.rejects(client().get("US0378331005"), (e: FundNotFound) => {
    assert.ok(e instanceof FundNotFound);
    assert.deepEqual(Object.keys(e.reasons), ["ishares", "vanguard", "spdr", "xtrackers", "amundi", "invesco"]);
    assert.ok(e.reasons["ishares"]!.includes("not in the iShares product index"));
    assert.ok(e.reasons["amundi"]!.includes("HTTP 404"));
    return true;
  });
});

test("an unavailable issuer is kept as a reason and the next one is asked", async () => {
  class Flaky extends RecordedTransport {
    override async request(method: string, url: string, options?: RequestOptions) {
      if (url.includes("ishares.com")) throw new TransportError("down");
      return super.request(method, url, options);
    }
  }
  const fund = await new HoldingsClient({ transport: new Flaky(), cacheDir: null }).get("IE000716YHJ7");
  assert.equal(fund.issuer, "invesco");
});

test("cache hit without a request", async () => {
  const t = new RecordedTransport();
  const c = new HoldingsClient({ transport: t, cacheDir: await tmp() });
  await c.get("IE000716YHJ7", { issuer: "invesco" });
  assert.equal(t.requests.length, 1);
  await c.get("IE000716YHJ7", { issuer: "invesco" });
  assert.equal(t.requests.length, 1);
});

test("a custom transport without cacheDir is not cached", async () => {
  const t = new RecordedTransport();
  const c = new HoldingsClient({ transport: t });
  await c.get("IE000716YHJ7", { issuer: "invesco" });
  await c.get("IE000716YHJ7", { issuer: "invesco" });
  assert.equal(t.requests.length, 2);
});

test("stale fallback when the network fails", async () => {
  const dir = await tmp();
  let now = 1000;
  const first = await new HoldingsClient({
    transport: new CachingTransport(new RecordedTransport(), dir, () => now),
    cacheDir: null,
  }).get("IE000716YHJ7", { issuer: "invesco" });
  assert.equal(first.stale, false);
  now += 7 * 3600;
  const again = await new HoldingsClient({
    transport: new CachingTransport(new StaticTransport(new TransportError("offline")), dir, () => now),
    cacheDir: null,
  }).get("IE000716YHJ7", { issuer: "invesco" });
  assert.equal(again.stale, true);
  assert.deepEqual(again.holdings, first.holdings);
});

test("zero holdings is unavailable", async () => {
  const t = new StaticTransport(reply(200, '{"effectiveDate": "2026-10-30", "holdings": []}', "application/json"));
  await assert.rejects(
    new HoldingsClient({ transport: t, cacheDir: null }).get("IE000716YHJ7", { issuer: "invesco" }),
    (e: FundNotFound) => e.reasons["invesco"]!.includes("no holdings"),
  );
});

test("getHoldings function", async () => {
  const fund = await getHoldings("IE000716YHJ7", { issuer: "invesco", transport: recordedTransport(), cacheDir: null });
  assert.equal(fund.issuer, "invesco");
});

// ------------------------------------------------------------ CachingTransport

class Script {
  calls = 0;
  constructor(private items: Array<HttpResponse | Error>) {}
  async request(): Promise<HttpResponse> {
    this.calls += 1;
    const item = this.items.shift()!;
    if (item instanceof Error) throw item;
    return item;
  }
}
const ok = (body = "hello") => new HttpResponse(200, new TextEncoder().encode(body), "text/plain", "https://x/a");

test("caching: fresh copy is returned without a request; params order does not matter", async () => {
  const inner = new Script([ok("one")]);
  const cache = new CachingTransport(inner, await tmp());
  const first = await cache.request("GET", "https://x/a", { params: { b: "2", a: "1" }, ttl: 60 });
  const second = await cache.request("GET", "https://x/a", { params: { a: "1", b: "2" }, ttl: 60 });
  assert.equal(first.text, "one");
  assert.equal(second.text, "one");
  assert.equal(inner.calls, 1);
  assert.equal(second.contentType, "text/plain");
  assert.equal(second.stale, false);
});

test("caching: ttl null never caches", async () => {
  const dir = await tmp();
  const cache = new CachingTransport(new Script([ok("one"), ok("two")]), dir);
  await cache.request("GET", "https://x/a");
  assert.equal((await cache.request("GET", "https://x/a")).text, "two");
  assert.deepEqual(await readdir(dir), []);
});

test("caching: expired copy is refetched; POST key uses canonical JSON; only 200 stored", async () => {
  let now = 1000;
  const cache = new CachingTransport(new Script([ok("one"), ok("two")]), await tmp(), () => now);
  await cache.request("GET", "https://x/a", { ttl: 60 });
  now += 61;
  assert.equal((await cache.request("GET", "https://x/a", { ttl: 60 })).text, "two");

  const post = new CachingTransport(new Script([ok("one"), ok("two")]), await tmp());
  await post.request("POST", "https://x/p", { json: { a: 1, b: 2 }, ttl: 60 });
  assert.equal((await post.request("POST", "https://x/p", { json: { b: 2, a: 1 }, ttl: 60 })).text, "one");
  assert.equal((await post.request("POST", "https://x/p", { json: { a: 1, b: 3 }, ttl: 60 })).text, "two");

  const errs = new CachingTransport(new Script([new HttpResponse(404, new Uint8Array(), "text/plain", "u"), ok("yes")]), await tmp());
  assert.equal((await errs.request("GET", "https://x/a", { ttl: 60 })).status, 404);
  assert.equal((await errs.request("GET", "https://x/a", { ttl: 60 })).text, "yes");
});

test("caching: stale copy on transport error and on 5xx; no copy means the error propagates", async () => {
  for (const failure of [new TransportError("down"), new HttpResponse(503, new Uint8Array(), "text/plain", "u")]) {
    let now = 1000;
    const cache = new CachingTransport(new Script([ok("old"), failure]), await tmp(), () => now);
    await cache.request("GET", "https://x/a", { ttl: 60 });
    now += 600;
    const resp = await cache.request("GET", "https://x/a", { ttl: 60 });
    assert.deepEqual([resp.text, resp.stale], ["old", true]);
  }
  await assert.rejects(new CachingTransport(new Script([new TransportError("down")]), await tmp()).request("GET", "https://x/a", { ttl: 60 }), TransportError);
  const r = await new CachingTransport(new Script([new HttpResponse(500, new Uint8Array(), "text/plain", "u")]), await tmp()).request("GET", "https://x/b", { ttl: 60 });
  assert.equal(r.status, 500);
});

test("response: text drops a BOM, json parses", () => {
  const r = new HttpResponse(200, new Uint8Array([0xef, 0xbb, 0xbf, 0x7b, 0x7d]), "application/json", "u");
  assert.equal(r.text, "{}");
  assert.deepEqual(r.json(), {});
});

const answer = (status: number, body = "x") => new HttpResponse(status, new TextEncoder().encode(body), "text/plain", "u");

test("caching: stale copy on 403, 408, 429, 500, 503; none on 404", async () => {
  for (const status of [403, 408, 429, 500, 503]) {
    let now = 1000;
    const cache = new CachingTransport(new Script([ok("old"), answer(status)]), await tmp(), () => now);
    await cache.request("GET", "https://x/a", { ttl: 60 });
    now += 600;
    const resp = await cache.request("GET", "https://x/a", { ttl: 60 });
    assert.deepEqual([resp.text, resp.stale], ["old", true], `status ${status}`);
  }
  let now = 1000;
  const cache = new CachingTransport(new Script([ok("old"), answer(404)]), await tmp(), () => now);
  await cache.request("GET", "https://x/a", { ttl: 60 });
  now += 600;
  assert.equal((await cache.request("GET", "https://x/a", { ttl: 60 })).status, 404);
});

const rejectBad = (r: HttpResponse) => {
  if (r.text === "bad") throw new Error("cannot parse");
};

test("caching: an answer the validator rejects is not kept; the previous copy is served stale", async () => {
  let now = 1000;
  const inner = new Script([ok("good"), ok("bad"), ok("good again")]);
  const cache = new CachingTransport(inner, await tmp(), () => now);
  await cache.request("GET", "https://x/a", { ttl: 60, validate: rejectBad });
  now += 600;
  const served = await cache.request("GET", "https://x/a", { ttl: 60, validate: rejectBad });
  assert.deepEqual([served.text, served.stale, served.storedAt], ["good", true, 1000]);
  assert.equal((await cache.request("GET", "https://x/a", { ttl: 60, validate: rejectBad })).text, "good again");
  assert.equal(inner.calls, 3);
});

test("caching: a rejected answer without a previous copy is returned uncached", async () => {
  const dir = await tmp();
  const inner = new Script([ok("bad"), ok("bad")]);
  const cache = new CachingTransport(inner, dir);
  const first = await cache.request("GET", "https://x/a", { ttl: 60, validate: rejectBad });
  assert.deepEqual([first.text, first.stale], ["bad", false]);
  await cache.request("GET", "https://x/a", { ttl: 60, validate: rejectBad });
  assert.equal(inner.calls, 2);
  assert.deepEqual(await readdir(dir), []);
});

test("caching: one file per key, no temporary file left, a corrupt file is a miss", async () => {
  const dir = await tmp();
  const cache = new CachingTransport(new Script([ok("one"), ok("two")]), dir);
  await cache.request("GET", "https://x/a", { ttl: 60 });
  const names = await readdir(dir);
  assert.equal(names.length, 1);
  assert.ok(names[0]!.endsWith(".cache"));
  await writeFile(join(dir, names[0]!), "not json at all");
  assert.equal((await cache.request("GET", "https://x/a", { ttl: 60 })).text, "two");
});

test("caching: storedAt of a cached copy is the store time", async () => {
  let now = 1000;
  const cache = new CachingTransport(new Script([ok("one")]), await tmp(), () => now);
  await cache.request("GET", "https://x/a", { ttl: 60 });
  now += 30;
  assert.equal((await cache.request("GET", "https://x/a", { ttl: 60 })).storedAt, 1000);
  assert.ok(ok().storedAt >= Date.now() / 1000 - 5);
});

test("caching: concurrent identical requests share one download", async () => {
  let calls = 0;
  const slow = {
    async request(): Promise<HttpResponse> {
      calls += 1;
      await new Promise((r) => setTimeout(r, 20));
      return ok("shared");
    },
  };
  const cache = new CachingTransport(slow, await tmp());
  const answers = await Promise.all([1, 2, 3].map(() => cache.request("GET", "https://x/a", { ttl: 60 })));
  assert.deepEqual(answers.map((a) => a.text), ["shared", "shared", "shared"]);
  assert.equal(calls, 1);
});

test("caching: a cache file the Python package wrote is served", async () => {
  const dir = await tmp();
  const cache = new CachingTransport(new Script([]), dir, () => 1010);
  // key and file as written by the Python CachingTransport for this request
  const key = "d79deda7d3c53886fc2a59802d1083f5a198175471232d8079e8466ef9eb9f48";
  await writeFile(join(dir, `${key}.cache`), '{"stored_at": 1000.5, "content_type": "text/plain", "url": "https://x/a"}\nbody');
  const served = await cache.request("POST", "https://x/a", {
    params: { b: "2", a: "1" },
    json: { k: "\u00e9", a: [1, 2.5, null] },
    ttl: 60,
  });
  assert.deepEqual([served.text, served.storedAt, served.url, served.stale], ["body", 1000.5, "https://x/a", false]);
});
