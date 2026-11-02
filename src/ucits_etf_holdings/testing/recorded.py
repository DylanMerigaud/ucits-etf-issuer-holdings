"""`RecordedTransport`: replays `recorded/index.json` instead of calling the network."""

from __future__ import annotations

import json as jsonlib
from pathlib import Path
from typing import Any

from ..http import Response

RECORDED_DIR = Path(__file__).parent / "recorded"

RECORDED_ISINS: tuple[str, ...] = (
    "IE00B4L5Y983",
    "IE00B3F81409",
    "IE00BK5BQT80",
    "LU0274211480",
    "IE000BI8OT95",
    "LU1681043599",
    "IE00B5M1WJ87",
    "IE000716YHJ7",
)


def _is_subset(expected: Any, actual: Any) -> bool:
    """True when `expected` is contained in `actual`: dicts recursively, everything else equal."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _is_subset(value, actual[key]) for key, value in expected.items()
        )
    return bool(expected == actual)


class RecordedTransport:
    """A `Transport` that answers from the recorded files and never touches the network."""

    def __init__(self, directory: Path = RECORDED_DIR) -> None:
        self._dir = directory
        index = jsonlib.loads((directory / "index.json").read_text(encoding="utf-8"))
        self._entries: list[dict[str, Any]] = index["entries"]
        self.requests: list[tuple[str, str]] = []

    def _matches(
        self, entry: dict[str, Any], method: str, url: str, params: dict[str, str] | None, body: Any
    ) -> bool:
        if entry["method"] != method.upper() or entry["url"] != url:
            return False
        if entry["params"] is not None:
            wanted = {k: str(v) for k, v in entry["params"].items()}
            if wanted != {k: str(v) for k, v in (params or {}).items()}:
                return False
        return entry["match_json"] is None or _is_subset(entry["match_json"], body)

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        ttl: float | None = None,
    ) -> Response:
        """Return the first recorded answer matching the request, or 404 `not recorded`."""
        self.requests.append((method.upper(), url))
        for entry in self._entries:
            if self._matches(entry, method, url, params, json):
                content = (self._dir / entry["file"]).read_bytes()
                return Response(entry["status"], content, entry["content_type"], url)
        return Response(404, b"not recorded", "text/plain", url)


def recorded_transport() -> RecordedTransport:
    """A fresh `RecordedTransport` over the files shipped in the package."""
    return RecordedTransport()
