"""Command line: `ucits-holdings ISIN [--issuer NAME] [--format json|csv|table] [--by KEY]`."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections.abc import Sequence

from . import __version__
from .client import HoldingsClient
from .errors import HoldingsError, InvalidISIN
from .http import Transport
from .issuers import ORDER
from .models import WEIGHT_KEYS, Fund

HOLDING_COLUMNS = (
    "name",
    "weight",
    "isin",
    "ticker",
    "country",
    "country_name",
    "sector",
    "currency",
    "asset_class",
    "asset_class_raw",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ucits-holdings",
        description="Print the holdings an issuer publishes for a UCITS ETF.",
    )
    parser.add_argument("isin", help="ISIN of the fund")
    parser.add_argument("--issuer", choices=ORDER, help="ask only this issuer")
    parser.add_argument("--format", choices=("json", "csv", "table"), default="json")
    parser.add_argument("--by", choices=WEIGHT_KEYS, help="group the weights by this field")
    parser.add_argument("--no-cache", action="store_true", help="do not read or write the cache")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _cell(value: object) -> str:
    return "" if value is None else str(value)


def _render_rows(header: Sequence[str], rows: list[list[str]], fmt: str) -> str:
    """Rows as CSV or as an aligned text table."""
    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
        return buffer.getvalue()
    widths = [
        max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(header)
    ]
    lines = ["  ".join(h.ljust(widths[i]) for i, h in enumerate(header)).rstrip()]
    lines += ["  ".join(c.ljust(widths[i]) for i, c in enumerate(r)).rstrip() for r in rows]
    return "\n".join(lines) + "\n"


def _render(fund: Fund, fmt: str, by: str | None) -> str:
    if by is not None:
        grouped = fund.weights_by(by)
        if fmt == "json":
            return json.dumps([{by: k, "weight": w} for k, w in grouped], indent=2) + "\n"
        rows = [[_cell(k), f"{w:g}"] for k, w in grouped]
        return _render_rows([by, "weight"], rows, fmt)
    if fmt == "json":
        return fund.to_json() + "\n"
    rows = [[_cell(getattr(h, col)) for col in HOLDING_COLUMNS] for h in fund.holdings]
    text = _render_rows(HOLDING_COLUMNS, rows, fmt)
    if fmt == "table":
        title = f"{fund.fund_name or fund.isin} ({fund.issuer}, as of {fund.as_of or 'unknown'})"
        return f"{title}\n\n{text}"
    return text


def main(argv: Sequence[str] | None = None, *, transport: Transport | None = None) -> int:
    """Run the command line; returns the exit code (0 ok, 1 not found, 2 bad input)."""
    args = _parser().parse_args(argv)
    options = {"cache_dir": None} if args.no_cache else {}
    try:
        with HoldingsClient(transport=transport, timeout=30.0, **options) as client:
            fund = client.get(args.isin, issuer=args.issuer)
    except InvalidISIN as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except HoldingsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(_render(fund, args.format, args.by))
    return 0


if __name__ == "__main__":
    sys.exit(main())
