import { nameOf, toIso2 } from "../countries.js";
import { IssuerUnavailable, TransportError } from "../errors.js";
import type { HttpResponse, RequestOptions, Transport } from "../http.js";
import { makeHoldingObject, type Fund, type Holding } from "../models.js";

/** Seconds an index answer (a fund list) may be cached. */
export const INDEX_TTL = 24 * 3600;
/** Seconds a holdings answer may be cached. */
export const HOLDINGS_TTL = 6 * 3600;

const LOOSE_ISIN = /^[A-Z]{2}[A-Z0-9]{9}[0-9]$/;
const NUMERIC = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/;

/** An issuer adapter: a `name` and a `fetch` returning the fund's holdings. */
export interface Issuer {
  readonly name: string;
  /** Return the fund, or throw NotListed or IssuerUnavailable. */
  fetch(isin: string, http: Transport): Promise<Fund>;
}

/** A stripped string, or null for null, blank and the dash placeholders issuers use. */
export function clean(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  return text === "" || text === "-" ? null : text;
}

/** An ISIN-shaped string or null (cash lines carry labels such as `_CURRENCYEUR`). */
export function cleanIsin(value: unknown): string | null {
  const text = clean(value);
  if (text === null) return null;
  const upper = text.toUpperCase();
  return LOOSE_ISIN.test(upper) ? upper : null;
}

/** A number for numbers and numeric strings; null otherwise (booleans included). */
export function number(value: unknown): number | null {
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const text = value.trim();
    return NUMERIC.test(text) ? Number(text) : null;
  }
  return null;
}

/** Optional fields of a holding, as an issuer gives them (any type, cleaned on the way in). */
export interface HoldingFields {
  isin?: unknown;
  ticker?: unknown;
  country?: unknown;
  country_name?: unknown;
  sector?: unknown;
  currency?: unknown;
  asset_class?: unknown;
}

/** Build a Holding, filling `country` from the name or `country_name` from the code. */
export function makeHolding(name: string, weight: number, fields: HoldingFields = {}): Holding {
  const given = fields.country;
  let code = given !== null && given !== undefined ? toIso2(clean(given)) : null;
  let label = clean(fields.country_name);
  if (code === null && label !== null) code = toIso2(label);
  if (label === null && code !== null) label = nameOf(code);
  return makeHoldingObject({
    name,
    weight,
    isin: cleanIsin(fields.isin),
    ticker: clean(fields.ticker),
    country: code,
    country_name: label,
    sector: clean(fields.sector),
    currency: clean(fields.currency),
    asset_class: clean(fields.asset_class),
  });
}

/** The current time as ISO 8601 UTC, without fractions, with a trailing Z. */
export function nowUtc(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

/** Send a request; a network failure becomes IssuerUnavailable. */
export async function call(
  issuer: string,
  http: Transport,
  method: string,
  url: string,
  options: RequestOptions = {},
): Promise<HttpResponse> {
  try {
    return await http.request(method, url, options);
  } catch (error) {
    if (error instanceof TransportError) {
      throw new IssuerUnavailable(issuer, `network error: ${error.message}`);
    }
    throw error;
  }
}

/** The parsed JSON of a 200 answer; anything else is IssuerUnavailable. */
export function okJson(issuer: string, response: HttpResponse): unknown {
  if (response.status !== 200) {
    throw new IssuerUnavailable(issuer, `HTTP ${response.status} from ${response.url}`);
  }
  try {
    return response.json();
  } catch {
    throw new IssuerUnavailable(issuer, `answer is not JSON (${response.url})`);
  }
}

/** The holdings; an empty list means the answer shape is not understood. */
export function requireHoldings(issuer: string, holdings: Holding[]): Holding[] {
  if (holdings.length === 0) throw new IssuerUnavailable(issuer, "the answer holds no holdings");
  return holdings;
}

/** A fund object with the schema's key order. */
export function makeFund(fund: Fund): Fund {
  return {
    isin: fund.isin,
    issuer: fund.issuer,
    fund_name: fund.fund_name,
    as_of: fund.as_of,
    currency: fund.currency,
    source_url: fund.source_url,
    fetched_at: fund.fetched_at,
    stale: fund.stale,
    holdings: fund.holdings,
  };
}
