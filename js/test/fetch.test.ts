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
  assert.ok(USER_AGENT.startsWith("ucits-etf-issuer-holdings/0.1.3 (+https://github.com/"));
  assert.equal(seen.origin, "https://o");
  assert.equal(seen.ct, "application/json");
  assert.equal(seen.body, '{"k":[1,2]}');
});

test("fetch transport: network errors become TransportError", async () => {
  await assert.rejects(new FetchTransport(2000, []).request("GET", "http://127.0.0.1:1/"), TransportError);
});

/** A server that cuts the connection of the first `drops` requests, then answers. */
async function withDrops(
  drops: number,
  status: number,
  run: (base: string, bodies: string[]) => Promise<void>,
): Promise<void> {
  const bodies: string[] = [];
  const server = createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      bodies.push(body);
      if (bodies.length <= drops) req.socket.destroy();
      else res.writeHead(status).end("{}");
    });
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  try {
    await run(`http://127.0.0.1:${(server.address() as AddressInfo).port}`, bodies);
  } finally {
    server.closeAllConnections();
    server.close();
  }
}

test("fetch transport: a dropped connection is retried with the same body", async () => {
  await withDrops(2, 200, async (base, bodies) => {
    const answer = await new FetchTransport(5000, [0, 0]).request("POST", `${base}/p`, { json: { k: 1 } });
    assert.equal(answer.status, 200);
    assert.deepEqual(bodies, ['{"k":1}', '{"k":1}', '{"k":1}']);
  });
});

test("fetch transport: gives up after the last retry", async (t) => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () => {
    calls += 1;
    throw new TypeError("fetch failed", {
      cause: Object.assign(new Error("connect ECONNREFUSED"), { code: "ECONNREFUSED" }),
    });
  });
  await assert.rejects(new FetchTransport(5000, [0, 0]).request("GET", "http://x/"), TransportError);
  assert.equal(calls, 3);
});

test("fetch transport: an answer is not retried, whatever its status", async () => {
  await withDrops(0, 503, async (base, bodies) => {
    assert.equal((await new FetchTransport(5000, [0, 0]).request("GET", base)).status, 503);
    assert.equal(bodies.length, 1);
  });
});

test("fetch transport: a connection that times out before it opens is retried", async (t) => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () => {
    calls += 1;
    if (calls < 3) {
      throw new TypeError("fetch failed", {
        cause: Object.assign(new Error("Connect Timeout Error"), { code: "UND_ERR_CONNECT_TIMEOUT" }),
      });
    }
    return new Response("{}", { status: 200 });
  });
  assert.equal((await new FetchTransport(5000, [0, 0]).request("GET", "http://x/")).status, 200);
  assert.equal(calls, 3);
});

test("fetch transport: a host name that does not resolve is retried, a timeout is not", async (t) => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () => {
    calls += 1;
    if (calls < 3) {
      throw new TypeError("fetch failed", {
        cause: Object.assign(new Error("getaddrinfo EAI_AGAIN x"), { code: "EAI_AGAIN" }),
      });
    }
    throw new DOMException("The operation was aborted due to timeout", "TimeoutError");
  });
  await assert.rejects(new FetchTransport(5000, [0, 0, 0, 0]).request("GET", "http://x/"), /timeout/);
  assert.equal(calls, 3);
});
