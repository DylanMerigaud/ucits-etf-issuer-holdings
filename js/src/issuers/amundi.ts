import { IssuerUnavailable, NotListed } from "../errors.js";
import type { HttpResponse, Transport } from "../http.js";
import type { Fund, Holding } from "../models.js";
import { isObject, pyRound, pyStr, truthy } from "../pyish.js";
import {
  HOLDINGS_TTL,
  asDict,
  fetchParsed,
  fetchedAt,
  isoDate,
  makeHolding,
  number,
  okJson,
  requireHoldings,
  text,
  type Issuer,
} from "./base.js";

const URL = "https://www.amundietf.de/mapi/ProductAPI/getProductsData";
const FIELDS = ["date", "type", "isin", "name", "weight", "currency", "sector", "countryOfRisk"];

type Obj = Record<string, unknown>;

/** The product, its holdings and the as-of date; an empty product list is NotListed. */
function parse(response: HttpResponse, isin: string): [Obj, Holding[], string | null] {
  const data = okJson("amundi", response);
  const products = isObject(data) ? data["products"] : undefined;
  if (!Array.isArray(products)) throw new IssuerUnavailable("amundi", "products missing in the answer");
  if (products.length === 0) throw new NotListed("amundi", isin, "the product list is empty");
  const product: unknown = products[0];
  const rows = isObject(product) ? asDict(product["composition"])["compositionData"] : undefined;
  if (!isObject(product) || !Array.isArray(rows)) {
    throw new IssuerUnavailable("amundi", "composition missing in the answer");
  }
  const holdings: Holding[] = [];
  const dates: string[] = [];
  for (const row of rows) {
    const item = isObject(row) ? asDict(row["compositionCharacteristics"]) : {};
    const weight = number(item["weight"]);
    if (weight === null || !truthy(item["name"])) continue;
    const date = isoDate(item["date"]);
    if (date !== null) dates.push(date);
    holdings.push(
      makeHolding(pyStr(item["name"]), pyRound(weight * 100, 10), {
        isin: item["isin"],
        country_name: item["countryOfRisk"],
        sector: item["sector"],
        currency: item["currency"],
        asset_class: item["type"],
      }),
    );
  }
  const asOf = dates.length > 0 ? dates.reduce((a, b) => (b > a ? b : a)) : null;
  return [product, requireHoldings("amundi", holdings), asOf];
}

/** Adapter for Amundi UCITS ETFs. Swap based funds publish their substitute basket. */
export class AmundiIssuer implements Issuer {
  readonly name = "amundi";

  /** Ask the product API for the ISIN; an empty product list means not listed. */
  async fetch(isin: string, http: Transport): Promise<Fund> {
    const body = {
      context: { countryCode: "DEU", languageCode: "de", userProfileName: "RETAIL" },
      productIds: [isin],
      productType: "PRODUCT",
      characteristics: ["SHARE_MARKETING_NAME"],
      composition: { compositionFields: FIELDS },
    };
    const [answer, [product, holdings, asOf]] = await fetchParsed(
      this.name,
      http,
      "POST",
      URL,
      (response) => parse(response, isin),
      { json: body, ttl: HOLDINGS_TTL },
    );
    return {
      isin,
      issuer: this.name,
      fund_name: text(asDict(product["characteristics"])["SHARE_MARKETING_NAME"]),
      as_of: asOf,
      currency: text(asDict(product["currencies"])["BASE_CURRENCY"]),
      source_url: URL,
      fetched_at: fetchedAt(answer),
      stale: answer.stale,
      holdings,
    };
  }
}
