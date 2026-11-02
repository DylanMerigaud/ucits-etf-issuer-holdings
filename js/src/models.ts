import { pyRound } from "./pyish.js";

/** The fields a holdings list can be grouped by. */
export type WeightKey = "country" | "sector" | "currency" | "asset_class";

/** The fields a holdings list can be grouped by, as a list. */
export const WEIGHT_KEYS: readonly WeightKey[] = ["country", "sector", "currency", "asset_class"];

/** The values `Holding.asset_class` takes (null when the issuer gives no class). */
export type AssetClass =
  | "equity"
  | "fixed_income"
  | "cash"
  | "derivative"
  | "fund"
  | "real_estate"
  | "commodity"
  | "other";

/** The values `Holding.asset_class` takes, as a list. */
export const ASSET_CLASSES: readonly AssetClass[] = [
  "equity",
  "fixed_income",
  "cash",
  "derivative",
  "fund",
  "real_estate",
  "commodity",
  "other",
];

/** One line of a fund. `weight` is a percent of the fund. */
export interface Holding {
  name: string;
  weight: number;
  isin: string | null;
  ticker: string | null;
  /** ISO 3166-1 alpha-2 code. */
  country: string | null;
  country_name: string | null;
  sector: string | null;
  currency: string | null;
  /** One of {@link ASSET_CLASSES}, or null when the issuer gives no class. */
  asset_class: string | null;
  /** The issuer's own asset class label. */
  asset_class_raw: string | null;
}

/** The holdings an issuer publishes for one fund, in the library's one JSON shape. */
export interface Fund {
  isin: string;
  issuer: string;
  fund_name: string | null;
  /** Date of the holdings, `YYYY-MM-DD`, or null. */
  as_of: string | null;
  currency: string | null;
  source_url: string;
  /** ISO 8601 UTC time the data was fetched. */
  fetched_at: string;
  /** True when the data comes from the cache because the issuer could not be reached. */
  stale: boolean;
  holdings: Holding[];
}

/** A value of the grouping key and its summed weight; the null bucket is the unknown values. */
export type WeightBucket = [value: string | null, weight: number];

/** Build a Holding with every field present, in the schema's key order. */
export function makeHoldingObject(
  fields: Pick<Holding, "name" | "weight"> & Partial<Holding>,
): Holding {
  return {
    name: fields.name,
    weight: fields.weight,
    isin: fields.isin ?? null,
    ticker: fields.ticker ?? null,
    country: fields.country ?? null,
    country_name: fields.country_name ?? null,
    sector: fields.sector ?? null,
    currency: fields.currency ?? null,
    asset_class: fields.asset_class ?? null,
    asset_class_raw: fields.asset_class_raw ?? null,
  };
}

function checkKey(key: string, label: string): asserts key is WeightKey {
  if (!(WEIGHT_KEYS as readonly string[]).includes(key)) {
    throw new RangeError(`${label} must be one of ${WEIGHT_KEYS.join(", ")}, got '${key}'`);
  }
}

/** Sum weights per value of a Holding field; largest first, the null bucket last. */
export function groupWeights(holdings: Iterable<Holding>, key: WeightKey): WeightBucket[] {
  const totals = new Map<string | null, number>();
  for (const holding of holdings) {
    const bucket = holding[key];
    totals.set(bucket, (totals.get(bucket) ?? 0) + holding.weight);
  }
  const ordered: WeightBucket[] = [];
  for (const [bucket, total] of totals) {
    if (bucket !== null) ordered.push([bucket, pyRound(total, 6)]);
  }
  ordered.sort((a, b) => b[1] - a[1]);
  if (totals.has(null)) ordered.push([null, pyRound(totals.get(null) as number, 6)]);
  return ordered;
}

/** Sum of the weights of a fund, in percent. */
export function totalWeight(fund: Fund): number {
  return fund.holdings.reduce((sum, h) => sum + h.weight, 0);
}

/**
 * Total weight per value of `key`, largest first, the null bucket last.
 *
 * @throws {RangeError} when `key` is not one of country, sector, currency, asset_class.
 */
export function weightsBy(fund: Fund, key: WeightKey): WeightBucket[] {
  checkKey(key, "key");
  return groupWeights(fund.holdings, key);
}

/** The `n` heaviest holdings of a fund (default 10). */
export function topHoldings(fund: Fund, n = 10): Holding[] {
  return [...fund.holdings].sort((a, b) => b.weight - a.weight).slice(0, n);
}

/** Throws a RangeError unless `key` is a valid grouping key. */
export function assertWeightKey(key: string, label: string): asserts key is WeightKey {
  checkKey(key, label);
}
