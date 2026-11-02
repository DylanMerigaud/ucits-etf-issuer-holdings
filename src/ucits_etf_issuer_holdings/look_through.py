"""Look-through: spread a portfolio of fund positions over what the funds hold."""

from __future__ import annotations

from collections.abc import Mapping

from .isin import normalize
from .models import WEIGHT_KEYS, Fund, Holding, group_weights


def look_through(
    positions: Mapping[str, float], funds: Mapping[str, Fund], by: str = "country"
) -> list[tuple[str | None, float]]:
    """Amount per value of `by` across all positions, largest first, the None bucket last.

    `positions` maps an ISIN to an amount; `funds` maps ISINs to their `Fund`. Each position is
    spread over the fund's holdings by weight. The part of a fund the issuer does not list is not
    counted, so the total can be below the sum of the positions.
    """
    if by not in WEIGHT_KEYS:
        raise ValueError(f"by must be one of {', '.join(WEIGHT_KEYS)}, got {by!r}")
    known = {normalize(isin): fund for isin, fund in funds.items()}
    scaled: list[Holding] = []
    for isin, amount in positions.items():
        fund = known.get(normalize(isin))
        if fund is None:
            raise KeyError(f"no fund given for position {isin}")
        scaled.extend(
            Holding(
                name=h.name,
                weight=h.weight * amount / 100.0,
                country=h.country,
                sector=h.sector,
                currency=h.currency,
                asset_class=h.asset_class,
                asset_class_raw=h.asset_class_raw,
            )
            for h in fund.holdings
        )
    return group_weights(scaled, by)
