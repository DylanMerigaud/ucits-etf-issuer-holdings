import { IssuerUnavailable, NotListed } from "../errors.js";
import { withParams, type HttpResponse, type Transport } from "../http.js";
import { unescapeHtml } from "../htmlEntities.js";
import type { Fund, Holding } from "../models.js";
import { isObject, pyStr, truthy } from "../pyish.js";
import {
  HOLDINGS_TTL,
  fetchParsed,
  fetchedAt,
  isoDate,
  makeHolding,
  number,
  okJson,
  requireHoldings,
  type Issuer,
} from "./base.js";

const URL = "https://dng-api.invesco.com/cache/v1/accounts/en_GB/shareclasses/{isin}/holdings/fund";
const PARAMS = { idType: "isin" };
const HEADERS = { Origin: "https://www.invesco.com" };

/** The holdings and the as-of date; 404 or an answer without `holdings` is NotListed. */
function parse(response: HttpResponse, isin: string): [Holding[], string | null] {
  if (response.status === 404) throw new NotListed("invesco", isin, "HTTP 404");
  const data = okJson("invesco", response);
  if (!isObject(data) || !("holdings" in data)) {
    throw new NotListed("invesco", isin, "the answer has no holdings");
  }
  const rows = data["holdings"];
  if (!Array.isArray(rows)) throw new IssuerUnavailable("invesco", "holdings is not a list");
  const holdings: Holding[] = [];
  for (const row of rows) {
    if (!isObject(row)) continue;
    const weight = number(row["weight"]);
    if (weight === null || !truthy(row["name"])) continue;
    holdings.push(
      makeHolding(unescapeHtml(pyStr(row["name"])), weight, {
        isin: row["isin"],
        currency: row["currency"],
      }),
    );
  }
  return [requireHoldings("invesco", holdings), isoDate(data["effectiveDate"])];
}

/** Adapter for Invesco UCITS ETFs. The file has no country, sector or fund name. */
export class InvescoIssuer implements Issuer {
  readonly name = "invesco";

  /** Read the holdings file; 404 or an answer without `holdings` means not listed. */
  async fetch(isin: string, http: Transport): Promise<Fund> {
    const url = URL.replace("{isin}", isin);
    const [answer, [holdings, asOf]] = await fetchParsed(
      this.name,
      http,
      "GET",
      url,
      (response) => parse(response, isin),
      { params: PARAMS, headers: HEADERS, ttl: HOLDINGS_TTL },
    );
    return {
      isin,
      issuer: this.name,
      fund_name: null,
      as_of: asOf,
      currency: null,
      source_url: withParams(url, PARAMS),
      fetched_at: fetchedAt(answer),
      stale: answer.stale,
      holdings,
    };
  }
}
