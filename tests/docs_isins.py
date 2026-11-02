"""The ISINs the README files and the examples tell a reader to run, and where each one runs.

0.1.0's flagship example was an iShares fund. iShares' CDN refuses most cloud and datacenter
addresses, so the first thing a reader ran on a server failed. `test_docs.py` (offline) keeps
every ISIN a reader runs against the live sites away from the issuers in DATACENTER_BLOCKED, and
`contract/test_docs_live.py` runs every documented ISIN against the live sites.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = (ROOT / "README.md", ROOT / "js" / "README.md")
EXAMPLES = tuple(sorted((ROOT / "examples").glob("*.py")))

# Issuers whose site refuses most cloud and datacenter addresses (measured 2026-11-02: iShares,
# Akamai "Access Denied" on www.ishares.com and www.blackrock.com from OVH, whatever the headers).
DATACENTER_BLOCKED = frozenset({"ishares"})

# The issuer of every ISIN the docs and examples name.
ISSUER_OF = {
    "IE00B4L5Y983": "ishares",
    "IE00BK5BQT80": "vanguard",
    "IE00BJ0KDQ92": "xtrackers",
    "LU0274211480": "xtrackers",
    "IE00B5M1WJ87": "spdr",
}
# Holdings named in an output sample, not funds.
NOT_FUNDS = frozenset({"US0378331005"})

_ISIN = re.compile(r"\b[A-Z]{2}[A-Z0-9]{9}[0-9]\b")
_FENCE = re.compile(r"^```(\w*)\n(.*?)^```", re.S | re.M)
_OFFLINE = re.compile(r"recorded_transport|recordedTransport")


def isins(text: str) -> list[str]:
    return [code for code in _ISIN.findall(text) if code not in NOT_FUNDS]


def live_text(path: Path) -> str:
    """The text of a doc a reader runs against the live sites: everything but the code blocks
    that replay recorded answers and the output samples (json and text blocks)."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        return "" if _OFFLINE.search(text) else text

    def keep(match: re.Match[str]) -> str:
        lang, body = match.group(1), match.group(2)
        return "" if lang in ("json", "text") or _OFFLINE.search(body) else body

    # a line that sends the request through a proxy is how a blocked issuer is meant to be read
    lines = _FENCE.sub(keep, text).splitlines()
    return "\n".join(line for line in lines if "--proxy" not in line and "proxy=" not in line)


def documented() -> list[str]:
    """Every fund ISIN the docs and the examples name, live or recorded, once each."""
    found: list[str] = []
    for path in (*DOCS, *EXAMPLES):
        found += isins(path.read_text(encoding="utf-8"))
    return list(dict.fromkeys(found))
