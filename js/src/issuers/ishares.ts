import { IssuerUnavailable, NotListed } from "../errors.js";
import { withParams, type Transport } from "../http.js";
import type { Fund, Holding } from "../models.js";
import { dig, isObject, pyStr, truthy } from "../pyish.js";
import {
  HOLDINGS_TTL,
  INDEX_TTL,
  call,
  makeHolding,
  nowUtc,
  number,
  okJson,
  requireHoldings,
  type Issuer,
} from "./base.js";

const INDEX_URL =
  "https://www.ishares.com/varnish-api/blk-product-screener-server/api/v1/product-screener/product-data";
const INDEX_PARAMS = {
  country: "de",
  language: "de",
  siteName: "de-ishares-v2",
  userType: "individual",
};
const HOLDINGS_URL =
  "https://www.ishares.com/varnish-api/uk-retail01-product-data/product-data/api/v2/get-product-data";

/** Unwrap the `{"r": raw, "d": display}` form some values come in. */
function raw(value: unknown): unknown {
  if (isObject(value) && "r" in value) return value["r"];
  return value;
}

/** `20261030` as `2026-10-30`. */
function asOf(value: unknown): string | null {
  const text = value !== null && value !== undefined ? pyStr(raw(value)) : "";
  if (text.length === 8 && /^\d+$/.test(text)) {
    return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6)}`;
  }
  return null;
}

/** Adapter for iShares UCITS ETFs. */
export class ISharesIssuer implements Issuer {
  readonly name = "ishares";

  /** Look the ISIN up in the screener index, then read the holdings component. */
  async fetch(isin: string, http: Transport): Promise<Fund> {
    const indexAnswer = await call(this.name, http, "GET", INDEX_URL, {
      params: INDEX_PARAMS,
      ttl: INDEX_TTL,
    });
    const index = okJson(this.name, indexAnswer);
    if (!isObject(index)) throw new IssuerUnavailable(this.name, "the product index is not an object");
    const entry = Object.values(index).find(
      (value) => isObject(value) && raw(value["isin"]) === isin,
    ) as Record<string, unknown> | undefined;
    if (entry === undefined) throw new NotListed(this.name, isin, "not in the iShares product index");
    const params = {
      appSubType: "ISHARES",
      appType: "PRODUCT_PAGE",
      component: "holdings",
      locale: "en_GB",
      portfolioId: pyStr(raw(entry["portfolioId"])),
      targetSite: "ishares-uk",
      userType: "individual",
      excludeContent: "true",
      includeConfig: "false",
    };
    const answer = await call(this.name, http, "GET", HOLDINGS_URL, { params, ttl: HOLDINGS_TTL });
    const data = okJson(this.name, answer);
    let points: Record<string, unknown>;
    let names: unknown[];
    let weights: unknown[];
    try {
      points = dig(
        data,
        "componentsByNameMap",
        "holdings",
        "containersByNameMap",
        "all",
        "dataPointsByNameMap",
      ) as Record<string, unknown>;
      names = dig(points, "issueName", "value") as unknown[];
      weights = dig(points, "holdingPercent", "value") as unknown[];
    } catch {
      throw new IssuerUnavailable(this.name, "holdings path missing in the answer");
    }
    const column = (key: string): unknown[] => {
      const point = points[key];
      const values = truthy(point) ? (point as Record<string, unknown>)["value"] : undefined;
      return Array.isArray(values) ? values : names.map(() => null);
    };
    const isins = column("isin");
    const tickers = column("ticker");
    const countries = column("countryOfRisk");
    const sectors = column("sectorName");
    const currencies = column("marketCurrencyCode");
    const classes = column("assetClass");
    const holdings: Holding[] = [];
    names.forEach((name, position) => {
      const weight = position < weights.length ? number(weights[position]) : null;
      if (weight === null || name === null || name === undefined) return;
      holdings.push(
        makeHolding(pyStr(name), weight, {
          isin: isins[position],
          ticker: tickers[position],
          country_name: countries[position],
          sector: sectors[position],
          currency: currencies[position],
          asset_class: classes[position],
        }),
      );
    });
    const dateColumn = points["asOfDate"];
    return {
      isin,
      issuer: this.name,
      fund_name: (raw(entry["fundName"]) ?? null) as string | null,
      as_of: asOf(truthy(dateColumn) ? (dateColumn as Record<string, unknown>)["value"] : undefined),
      currency: (raw(entry["seriesBaseCurrencyCode"]) ?? null) as string | null,
      source_url: withParams(HOLDINGS_URL, params),
      fetched_at: nowUtc(),
      stale: indexAnswer.stale || answer.stale,
      holdings: requireHoldings(this.name, holdings),
    };
  }
}
