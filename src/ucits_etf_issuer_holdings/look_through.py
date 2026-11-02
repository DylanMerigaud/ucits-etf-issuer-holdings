"""Look-through: spread a portfolio of fund positions over what the funds hold."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from .isin import normalize
from .models import WEIGHT_KEYS, Fund, Holding, group_pairs, group_weights

# `isin` groups by single name: the holding's ISIN, or its name when the issuer gives no ISIN.
LOOK_THROUGH_KEYS = (*WEIGHT_KEYS, "isin")


def look_through(
    positions: Mapping[str, float], funds: Mapping[str, Fund], by: str = "country"
) -> list[tuple[str | None, float]]:
    """Amount per value of `by` across all positions, largest first, the None bucket last.

    `by` is one of `LOOK_THROUGH_KEYS`: country, sector, currency, asset_class, or isin for a
    single-name concentration (a holding without an ISIN is counted under its name).

    `positions` maps an ISIN to an amount; `funds` maps ISINs to their `Fund`. Each position is
    spread over the fund's holdings by weight. The part of a fund the issuer does not list is not
    counted, so the total can be below the sum of the positions.
    """
    if by not in LOOK_THROUGH_KEYS:
        raise ValueError(f"by must be one of {', '.join(LOOK_THROUGH_KEYS)}, got {by!r}")
    known = {normalize(isin): fund for isin, fund in funds.items()}
    scaled: list[Holding] = []
    for isin, amount in positions.items():
        fund = known.get(normalize(isin))
        if fund is None:
            raise KeyError(f"no fund given for position {isin}")
        scaled.extend(replace(h, weight=h.weight * amount / 100.0) for h in fund.holdings)
    if by == "isin":
        return group_pairs((h.isin or h.name or None, h.weight) for h in scaled)
    return group_weights(scaled, by)
