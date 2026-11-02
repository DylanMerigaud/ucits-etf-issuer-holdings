"""HTTP layer: `Response`, the `Transport` protocol, `HttpxTransport` and `CachingTransport`."""

from __future__ import annotations

import hashlib
import json as jsonlib
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

import httpx

from . import __version__
from .errors import TransportError

USER_AGENT = (
    f"ucits-etf-issuer-holdings/{__version__} "
    "(+https://github.com/DylanMerigaud/ucits-etf-issuer-holdings)"
)

DEFAULT_CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / (
    "ucits-etf-issuer-holdings"
)


@dataclass(frozen=True)
class Response:
    """What a transport returns: status, raw body, content type, final url."""

    status: int
    content: bytes
    content_type: str
    url: str
    stale: bool = False

    @property
    def text(self) -> str:
        """The body decoded as UTF-8 (a leading byte order mark is dropped)."""
        return self.content.decode("utf-8-sig", errors="replace")

    def json(self) -> Any:
        """The body parsed as JSON."""
        return jsonlib.loads(self.content)


class Transport(Protocol):
    """Anything that can perform a request and return a `Response`."""

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
        """Perform the request. `ttl` (seconds) lets a caching layer keep the answer."""
        ...


class HttpxTransport:
    """Real network transport on httpx. Proxy variables (HTTPS_PROXY, ALL_PROXY) are honoured."""

    def __init__(self, timeout: float = 30.0, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=timeout, follow_redirects=True, trust_env=True
        )

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
        """Send the request with the library's user agent; network errors become TransportError."""
        merged = {"User-Agent": USER_AGENT, **(headers or {})}
        try:
            answer = self._client.request(method, url, params=params, json=json, headers=merged)
        except httpx.HTTPError as exc:
            raise TransportError(f"{method} {url}: {exc}") from exc
        return Response(
            status=answer.status_code,
            content=answer.content,
            content_type=answer.headers.get("content-type", ""),
            url=str(answer.url),
        )


class CachingTransport:
    """Wraps a transport with an on-disk cache of 200 answers.

    A copy younger than `ttl` is returned without a request. When the live request fails with a
    `TransportError` or answers 500 or more and an older copy exists, that copy is returned with
    `stale=True`.
    """

    def __init__(
        self,
        inner: Transport,
        cache_dir: str | Path,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._inner = inner
        self._dir = Path(cache_dir)
        self._clock = clock

    @staticmethod
    def _key(method: str, url: str, params: dict[str, str] | None, body: Any) -> str:
        parts = [
            method.upper(),
            url,
            jsonlib.dumps(sorted((params or {}).items())),
            jsonlib.dumps(body, sort_keys=True, separators=(",", ":")),
        ]
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()

    def _load(self, key: str) -> tuple[Response, float] | None:
        try:
            meta = jsonlib.loads((self._dir / f"{key}.json").read_text())
            body = (self._dir / f"{key}.body").read_bytes()
            response = Response(200, body, meta["content_type"], meta["url"])
            return response, float(meta["stored_at"])
        except (OSError, ValueError, KeyError):
            return None

    def _store(self, key: str, response: Response) -> None:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            meta = {
                "stored_at": self._clock(),
                "content_type": response.content_type,
                "url": response.url,
            }
            (self._dir / f"{key}.body").write_bytes(response.content)
            (self._dir / f"{key}.json").write_text(jsonlib.dumps(meta))
        except OSError:
            return  # a cache that cannot be written is not an error

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
        """Serve from cache when fresh, else ask the inner transport, falling back to stale."""
        if ttl is None:
            return self._inner.request(
                method, url, params=params, json=json, headers=headers, ttl=None
            )
        key = self._key(method, url, params, json)
        cached = self._load(key)
        if cached is not None and self._clock() - cached[1] < ttl:
            return cached[0]
        try:
            live = self._inner.request(
                method, url, params=params, json=json, headers=headers, ttl=ttl
            )
        except TransportError:
            if cached is None:
                raise
            return replace(cached[0], stale=True)
        if live.status >= 500 and cached is not None:
            return replace(cached[0], stale=True)
        if live.status == 200:
            self._store(key, live)
        return live
