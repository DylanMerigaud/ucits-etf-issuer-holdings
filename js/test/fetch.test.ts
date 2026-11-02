import assert from "node:assert/strict";
import { createServer, type IncomingMessage } from "node:http";
import type { AddressInfo } from "node:net";
import { test } from "node:test";
import { FetchTransport, TransportError, USER_AGENT } from "../dist/index.js";

async function withServer<T>(
  handler: (req: IncomingMessage, body: string) => [number, string],
  run: (base: string) => Promise<T>,
): Promise<T> {
  const server = createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      const [status, text] = handler(req, body);
      res.writeHead(status, { "content-type": "application/json" }).end(text);
    });
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  try {
    return await run(`http://127.0.0.1:${(server.address() as AddressInfo).port}`);
  } finally {
    server.close();
  }
}

test("fetch transport: user agent, params, headers, JSON body", async () => {
  let seen: { url?: string; ua?: string; origin?: string; ct?: string; body?: string; method?: string } = {};
  await withServer(
    (req, body) => {
      seen = { url: req.url, ua: req.headers["user-agent"], origin: req.headers["origin"] as string, ct: req.headers["content-type"], body, method: req.method };
      return [200, '{"ok":true}'];
    },
    async (base) => {
      const t = new FetchTransport(5000);
      const r = await t.request("POST", `${base}/p`, { params: { x: "1", y: "a b" }, json: { k: [1, 2] }, headers: { Origin: "https://o" } });
      assert.equal(r.status, 200);
      assert.deepEqual(r.json(), { ok: true });
      assert.equal(r.contentType, "application/json");
    },
  );
  assert.equal(seen.url, "/p?x=1&y=a+b");
  assert.equal(seen.ua, USER_AGENT);
  assert.ok(USER_AGENT.startsWith("ucits-etf-issuer-holdings/0.1.0 (+https://github.com/"));
  assert.equal(seen.origin, "https://o");
  assert.equal(seen.ct, "application/json");
  assert.equal(seen.body, '{"k":[1,2]}');
});

test("fetch transport: network errors become TransportError", async () => {
  await assert.rejects(new FetchTransport(2000).request("GET", "http://127.0.0.1:1/"), TransportError);
});
