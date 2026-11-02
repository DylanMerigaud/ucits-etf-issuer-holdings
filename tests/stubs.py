"""Transports used by the tests. None of them touches the network."""

from __future__ import annotations

import json as jsonlib
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from ucits_etf_holdings.http import Response
from ucits_etf_holdings.testing import RecordedTransport

Rewrite = Callable[[str, str, Response], Response]


class RewritingTransport:
    """Replays the recorded answers, passing each through `rewrite` (to fake a shape change)."""

    def __init__(self, rewrite: Rewrite) -> None:
        self.inner = RecordedTransport()
        self.rewrite = rewrite
        self.calls = 0

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
        self.calls += 1
        answer = self.inner.request(method, url, params=params, json=json, headers=headers)
        return self.rewrite(method, url, answer)


def with_json(response: Response, data: Any) -> Response:
    """The same response with a different JSON body."""
    return replace(response, content=jsonlib.dumps(data).encode())


class StaticTransport:
    """Answers every request with the same response, or raises the given exception."""

    def __init__(self, answer: Response | Exception) -> None:
        self.answer = answer
        self.requests: list[tuple[str, str, dict[str, str] | None, Any, dict[str, str] | None]] = []

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
        self.requests.append((method, url, params, json, headers))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer
