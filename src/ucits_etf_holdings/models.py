"""The normalised shapes: `Holding` and `Fund`."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

WEIGHT_KEYS = ("country", "sector", "currency", "asset_class")


@dataclass(frozen=True)
class Holding:
    """One line of a fund. `weight` is a percent of the fund."""

    name: str
    weight: float
    isin: str | None = None
    ticker: str | None = None
    country: str | None = None
    country_name: str | None = None
    sector: str | None = None
    currency: str | None = None
    asset_class: str | None = None


@dataclass(frozen=True)
class Fund:
    """The holdings an issuer publishes for one fund, in the library's one shape."""

    isin: str
    issuer: str
    fund_name: str | None
    as_of: str | None
    currency: str | None
    source_url: str
    fetched_at: str
    stale: bool
    holdings: tuple[Holding, ...]

    @property
    def total_weight(self) -> float:
        """Sum of the weights, in percent."""
        return sum(h.weight for h in self.holdings)

    def weights_by(self, key: str) -> list[tuple[str | None, float]]:
        """Total weight per value of `key`, largest first, the None bucket last."""
        if key not in WEIGHT_KEYS:
            raise ValueError(f"key must be one of {', '.join(WEIGHT_KEYS)}, got {key!r}")
        return group_weights(self.holdings, key)

    def top(self, n: int = 10) -> list[Holding]:
        """The `n` heaviest holdings."""
        return sorted(self.holdings, key=lambda h: h.weight, reverse=True)[:n]

    def to_dict(self) -> dict[str, Any]:
        """A JSON-ready dict following `schema/fund.schema.json`."""
        data = asdict(self)
        data["holdings"] = [asdict(h) for h in self.holdings]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Fund:
        """Rebuild a Fund from `to_dict()` output."""
        return cls(
            isin=data["isin"],
            issuer=data["issuer"],
            fund_name=data.get("fund_name"),
            as_of=data.get("as_of"),
            currency=data.get("currency"),
            source_url=data["source_url"],
            fetched_at=data["fetched_at"],
            stale=bool(data.get("stale", False)),
            holdings=tuple(Holding(**h) for h in data["holdings"]),
        )

    def to_json(self, indent: int | None = 2) -> str:
        """The fund as a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def group_weights(holdings: Iterable[Holding], key: str) -> list[tuple[str | None, float]]:
    """Sum weights per value of a Holding attribute; largest first, None last."""
    totals: dict[str | None, float] = {}
    for holding in holdings:
        bucket = getattr(holding, key)
        totals[bucket] = totals.get(bucket, 0.0) + holding.weight
    ordered: list[tuple[str | None, float]] = sorted(
        ((k, round(v, 6)) for k, v in totals.items() if k is not None),
        key=lambda item: item[1],
        reverse=True,
    )
    if None in totals:
        ordered.append((None, round(totals[None], 6)))
    return ordered
