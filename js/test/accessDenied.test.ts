// A site that refuses the caller's network address (iShares behind Akamai, from a datacenter):
// AccessDenied naming the cause, and FundNotFound.blocked naming the issuer.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  AccessDenied,
  FundNotFound,
  HoldingsClient,
  HttpResponse,
  IssuerUnavailable,
  type RequestOptions,
} from "../dist/index.js";
import { ISSUERS } from "../dist/issuers/index.js";
import { RecordedTransport } from "../dist/testing.js";
import { StaticTransport } from "./stubs.js";

// The body Akamai sent to this library from an OVH address on 2026-11-02 (reference trimmed).
const AKAMAI_403 =
  "<HTML><HEAD>\n<TITLE>Access Denied</TITLE>\n</HEAD><BODY>\n<H1>Access Denied</H1>\n \n" +
  "You don't have permission to access \"http&#58;&#47;&#47;www&#46;ishares&#46;com&#47;\" " +
  "on this server.<P>\nReference&#32;&#35;18&#46;0\n</BODY>\n</HTML>\n";
const URL_403 = "https://www.ishares.com/varnish-api/x";

const refused = (url = URL_403, status = 403) =>
  new HttpResponse(status, new TextEncoder().encode(AKAMAI_403), "text/html", url);

/** Replays the recorded answers, except that one host answers Akamai's 403. */
class BlockedHost extends RecordedTransport {
  constructor(private readonly host: string) {
    super();
  }
  override async request(method: string, url: string, options: RequestOptions = {}): Promise<HttpResponse> {
    return url.includes(this.host) ? refused(url) : super.request(method, url, options);
  }
}

for (const name of ["ishares", "vanguard", "spdr"]) {
  test(`${name}: a 403 is AccessDenied naming the cause`, async () => {
    await assert.rejects(ISSUERS[name]!.fetch("IE00B4L5Y983", new StaticTransport(refused())), (error) => {
      assert.ok(error instanceof AccessDenied);
      assert.ok(error instanceof IssuerUnavailable);
      assert.equal(error.issuer, name);
      assert.equal(error.url, URL_403);
      assert.match(error.message, /refused this network address/);
      assert.match(error.reason, /datacenter/);
      return true;
    });
  });
}

test("other statuses stay IssuerUnavailable", async () => {
  await assert.rejects(
    ISSUERS["ishares"]!.fetch("IE00B4L5Y983", new StaticTransport(refused(URL_403, 503))),
    (error) => error instanceof IssuerUnavailable && !(error instanceof AccessDenied),
  );
});

test("FundNotFound says which issuer refused", async () => {
  const client = new HoldingsClient({ transport: new BlockedHost("ishares.com"), cacheDir: null });
  await assert.rejects(client.get("IE00B4L5Y983"), (error) => {
    assert.ok(error instanceof FundNotFound);
    assert.deepEqual(error.blocked, ["ishares"]);
    assert.ok(
      error.message.startsWith(
        "IE00B4L5Y983: no issuer returned holdings, and ishares refused this network address",
      ),
    );
    return true;
  });
});

test("the other issuers still answer when one refuses", async () => {
  const client = new HoldingsClient({ transport: new BlockedHost("ishares.com"), cacheDir: null });
  assert.equal((await client.get("IE00BK5BQT80")).issuer, "vanguard");
});

test("nothing blocked keeps the plain message", async () => {
  const client = new HoldingsClient({ transport: new RecordedTransport(), cacheDir: null });
  await assert.rejects(client.get("US0378331005"), (error) => {
    assert.ok(error instanceof FundNotFound);
    assert.deepEqual(error.blocked, []);
    assert.ok(error.message.startsWith("US0378331005: no issuer returned holdings ("));
    return true;
  });
});
