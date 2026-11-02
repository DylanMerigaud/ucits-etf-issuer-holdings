import { IssuerUnavailable, NotListed } from "../errors.js";
import type { Transport } from "../http.js";
import type { Fund, Holding } from "../models.js";
import { dig, isObject, pyRound, pyStr, truthy } from "../pyish.js";
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

const URL = "https://www.amundietf.de/mapi/ProductAPI/getProductsData";
const FIELDS = ["date", "type", "isin", "name", "weight", "currency", "sector", "countryOfRisk"];

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
    const answer = await call(this.name, http, "POST", URL, { json: body, ttl: HOLDINGS_TTL });
    const data = okJson(this.name, answer);
    const products = isObject(data) ? data["products"] : undefined;
    if (!Array.isArray(products)) {
      throw new IssuerUnavailable(this.name, "products missing in the answer");
    }
    if (products.length === 0) throw new NotListed(this.name, isin, "the product list is empty");
    const product = products[0] as Record<string, unknown>;
    let rows: unknown[];
    try {
      rows = dig(product, "composition", "compositionData") as unknown[];
    } catch {
      throw new IssuerUnavailable(this.name, "composition missing in the answer");
    }
    const holdings: Holding[] = [];
    const dates: string[] = [];
    for (const row of rows) {
      const raw = (row as Record<string, unknown>)["compositionCharacteristics"];
      const item = (truthy(raw) ? raw : {}) as Record<string, unknown>;
      const weight = number(item["weight"]);
      if (weight === null || !truthy(item["name"])) continue;
      if (truthy(item["date"])) dates.push(pyStr(item["date"]));
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
    const characteristics = product["characteristics"];
    const currencies = product["currencies"];
    return {
      isin,
      issuer: this.name,
      fund_name: ((truthy(characteristics) ? (characteristics as Record<string, unknown>) : {})[
        "SHARE_MARKETING_NAME"
      ] ?? null) as string | null,
      as_of: dates.length > 0 ? dates.reduce((a, b) => (b > a ? b : a)) : null,
      currency: ((truthy(currencies) ? (currencies as Record<string, unknown>) : {})[
        "BASE_CURRENCY"
      ] ?? null) as string | null,
      source_url: URL,
      fetched_at: nowUtc(),
      stale: answer.stale,
      holdings: requireHoldings(this.name, holdings),
    };
  }
}
