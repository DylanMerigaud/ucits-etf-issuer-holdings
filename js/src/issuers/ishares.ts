import { IssuerUnavailable, NotListed } from "../errors.js";
import { withParams, type HttpResponse, type Transport } from "../http.js";
import type { Fund, Holding } from "../models.js";
import { isObject, pyStr } from "../pyish.js";
import {
  HOLDINGS_TTL,
  INDEX_TTL,
  asDict,
  fetchParsed,
  fetchedAt,
  makeHolding,
  number,
  okJson,
  requireHoldings,
  text,
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

function parseIndex(response: HttpResponse): Record<string, unknown> {
  const index = okJson("ishares", response);
  if (!isObject(index)) throw new IssuerUnavailable("ishares", "the product index is not an object");
  return index;
}

/** The holdings and the as-of date of a holdings component answer. */
function parseHoldings(response: HttpResponse): [Holding[], string | null] {
  let node: unknown = okJson("ishares", response);
  for (const key of ["componentsByNameMap", "holdings", "containersByNameMap", "all", "dataPointsByNameMap"]) {
    node = isObject(node) ? node[key] : undefined;
  }
  const points = node;
  const names = isObject(points) ? asDict(points["issueName"])["value"] : undefined;
  const weights = isObject(points) ? asDict(points["holdingPercent"])["value"] : undefined;
  if (!isObject(points) || !Array.isArray(names) || !Array.isArray(weights)) {
    throw new IssuerUnavailable("ishares", "holdings path missing in the answer");
  }
  const column = (key: string): unknown[] => {
    const raw = asDict(points[key])["value"];
    const values = Array.isArray(raw) ? raw : [];
    return names.map((_, i) => (i < values.length ? values[i] : null));
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
        issuer: "ishares",
      }),
    );
  });
  return [requireHoldings("ishares", holdings), asOf(asDict(points["asOfDate"])["value"])];
}

/** Adapter for iShares UCITS ETFs. */
export class ISharesIssuer implements Issuer {
  readonly name = "ishares";

  /** Look the ISIN up in the screener index, then read the holdings component. */
  async fetch(isin: string, http: Transport): Promise<Fund> {
    const [indexAnswer, index] = await fetchParsed(this.name, http, "GET", INDEX_URL, parseIndex, {
      params: INDEX_PARAMS,
      ttl: INDEX_TTL,
    });
    const entry = Object.values(index).find(
      (value) => isObject(value) && raw(value["isin"]) === isin,
    ) as Record<string, unknown> | undefined;
    if (entry === undefined) throw new NotListed(this.name, isin, "not in the iShares product index");
    const portfolioId = raw(entry["portfolioId"]);
    const usable =
      (typeof portfolioId === "string" || (typeof portfolioId === "number" && Number.isInteger(portfolioId))) &&
      String(portfolioId).trim() !== "";
    if (!usable) throw new IssuerUnavailable(this.name, "portfolioId missing for the fund");
    const params = {
      appSubType: "ISHARES",
      appType: "PRODUCT_PAGE",
      component: "holdings",
      locale: "en_GB",
      portfolioId: String(portfolioId),
      targetSite: "ishares-uk",
      userType: "individual",
      excludeContent: "true",
      includeConfig: "false",
    };
    const [answer, [holdings, asOfDate]] = await fetchParsed(
      this.name,
      http,
      "GET",
      HOLDINGS_URL,
      parseHoldings,
      { params, ttl: HOLDINGS_TTL },
    );
    return {
      isin,
      issuer: this.name,
      fund_name: text(raw(entry["fundName"])),
      as_of: asOfDate,
      currency: text(raw(entry["seriesBaseCurrencyCode"])),
      source_url: withParams(HOLDINGS_URL, params),
      fetched_at: fetchedAt(indexAnswer, answer),
      stale: indexAnswer.stale || answer.stale,
      holdings,
    };
  }
}
