import { normalizeIsin } from "./isin.js";
import { assertWeightKey, groupWeights, type Fund, type Holding, type WeightBucket, makeHoldingObject } from "./models.js";

/**
 * Amount per value of `by` across all positions, largest first, the null bucket last.
 *
 * `positions` maps an ISIN to an amount; `funds` maps ISINs to their fund. Each position is
 * spread over the fund's holdings by weight. The part of a fund the issuer does not list is not
 * counted, so the total can be below the sum of the positions.
 *
 * @throws {RangeError} when `by` is not a grouping key.
 * @throws {Error} when a position has no fund in `funds`.
 */
export function lookThrough(
  positions: Readonly<Record<string, number>>,
  funds: Readonly<Record<string, Fund>>,
  by: string = "country",
): WeightBucket[] {
  assertWeightKey(by, "by");
  const known = new Map<string, Fund>();
  for (const [isin, fund] of Object.entries(funds)) known.set(normalizeIsin(isin), fund);
  const scaled: Holding[] = [];
  for (const [isin, amount] of Object.entries(positions)) {
    const fund = known.get(normalizeIsin(isin));
    if (fund === undefined) throw new Error(`no fund given for position ${isin}`);
    for (const h of fund.holdings) {
      scaled.push(
        makeHoldingObject({
          name: h.name,
          weight: (h.weight * amount) / 100,
          country: h.country,
          sector: h.sector,
          currency: h.currency,
          asset_class: h.asset_class,
        }),
      );
    }
  }
  return groupWeights(scaled, by);
}
