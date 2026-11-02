import { normalizeIsin } from "./isin.js";
import { WEIGHT_KEYS, groupPairs, groupWeights, type Fund, type Holding, type WeightBucket, type WeightKey } from "./models.js";

/** The keys {@link lookThrough} groups by: a {@link WeightKey}, or `isin` for single names. */
export type LookThroughKey = WeightKey | "isin";

/** The keys {@link lookThrough} groups by, as a list. */
export const LOOK_THROUGH_KEYS: readonly LookThroughKey[] = [...WEIGHT_KEYS, "isin"];

/**
 * Amount per value of `by` across all positions, largest first, the null bucket last.
 *
 * `positions` maps an ISIN to an amount; `funds` maps ISINs to their fund. Each position is
 * spread over the fund's holdings by weight. The part of a fund the issuer does not list is not
 * counted, so the total can be below the sum of the positions. `by` is one of
 * {@link LOOK_THROUGH_KEYS}: `isin` gives a single-name concentration, a holding without an
 * ISIN being counted under its name.
 *
 * @throws {RangeError} when `by` is not one of {@link LOOK_THROUGH_KEYS}.
 * @throws {Error} when a position has no fund in `funds`.
 */
export function lookThrough(
  positions: Readonly<Record<string, number>>,
  funds: Readonly<Record<string, Fund>>,
  by: string = "country",
): WeightBucket[] {
  if (!(LOOK_THROUGH_KEYS as readonly string[]).includes(by)) {
    throw new RangeError(`by must be one of ${LOOK_THROUGH_KEYS.join(", ")}, got '${by}'`);
  }
  const known = new Map<string, Fund>();
  for (const [isin, fund] of Object.entries(funds)) known.set(normalizeIsin(isin), fund);
  const scaled: Holding[] = [];
  for (const [isin, amount] of Object.entries(positions)) {
    const fund = known.get(normalizeIsin(isin));
    if (fund === undefined) throw new Error(`no fund given for position ${isin}`);
    for (const h of fund.holdings) scaled.push({ ...h, weight: (h.weight * amount) / 100 });
  }
  if (by === "isin") return groupPairs(scaled.map((h): WeightBucket => [h.isin || h.name || null, h.weight]));
  return groupWeights(scaled, by as WeightKey);
}
