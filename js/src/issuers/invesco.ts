import { IssuerUnavailable, NotListed } from "../errors.js";
import { withParams, type Transport } from "../http.js";
import { unescapeHtml } from "../htmlEntities.js";
import type { Fund, Holding } from "../models.js";
import { isObject, pyStr, truthy } from "../pyish.js";
import {
  HOLDINGS_TTL,
  call,
  makeHolding,
  nowUtc,
  number,
  okJson,
  requireHoldings,
  type Issuer,
} from "./base.js";

const URL = "https://dng-api.invesco.com/cache/v1/accounts/en_GB/shareclasses/{isin}/holdings/fund";
const PARAMS = { idType: "isin" };
const HEADERS = { Origin: "https://www.invesco.com" };

/** Adapter for Invesco UCITS ETFs. The file has no country, sector or fund name. */
export class InvescoIssuer implements Issuer {
  readonly name = "invesco";

  /** Read the holdings file; 404 or an answer without `holdings` means not listed. */
  async fetch(isin: string, http: Transport): Promise<Fund> {
    const url = URL.replace("{isin}", isin);
    const answer = await call(this.name, http, "GET", url, {
      params: PARAMS,
      headers: HEADERS,
      ttl: HOLDINGS_TTL,
    });
    if (answer.status === 404) throw new NotListed(this.name, isin, "HTTP 404");
    const data = okJson(this.name, answer);
    if (!isObject(data) || !("holdings" in data)) {
      throw new NotListed(this.name, isin, "the answer has no holdings");
    }
    const rows = data["holdings"];
    if (!Array.isArray(rows)) throw new IssuerUnavailable(this.name, "holdings is not a list");
    const holdings: Holding[] = [];
    for (const row of rows as Array<Record<string, unknown>>) {
      const weight = number(row["weight"]);
      if (weight === null || !truthy(row["name"])) continue;
      holdings.push(
        makeHolding(unescapeHtml(pyStr(row["name"])), weight, {
          isin: row["isin"],
          currency: row["currency"],
        }),
      );
    }
    return {
      isin,
      issuer: this.name,
      fund_name: null,
      as_of: (data["effectiveDate"] ?? null) as string | null,
      currency: null,
      source_url: withParams(url, PARAMS),
      fetched_at: nowUtc(),
      stale: answer.stale,
      holdings: requireHoldings(this.name, holdings),
    };
  }
}
