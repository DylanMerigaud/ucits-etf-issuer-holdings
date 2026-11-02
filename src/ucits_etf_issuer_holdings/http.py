"""HTTP layer: `Response`, the `Transport` protocol, `HttpxTransport` and `CachingTransport`."""

from __future__ import annotations

import hashlib
import json as jsonlib
import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
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
    """What a transport returns: status, raw body, content type, final url.

    `stored_at` is when the body was fetched from the issuer, in seconds since the epoch (UTC):
    now for a live answer, the time it was stored for a cached or stale copy.
    """

    status: int
    content: bytes
    content_type: str
    url: str
    stale: bool = False
    stored_at: float = field(default_factory=time.time)

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
        self._owned = client is None
        self._client = client or httpx.Client(
            timeout=timeout, follow_redirects=True, trust_env=True
        )

    def close(self) -> None:
        """Close the httpx client this transport made (a client you passed stays open)."""
        if self._owned:
            self._client.close()

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


Validate = Callable[[Response], object]

# Statuses after which a stale copy is served when one exists: refused, timed out, rate limited.
STALE_ON = frozenset({403, 408, 429})


class CachingTransport:
    """Wraps a transport with an on-disk cache of 200 answers.

    A copy younger than `ttl` is returned without a request. When the live request fails with a
    `TransportError`, or answers 403, 408, 429 or 500 and above, and an older copy exists, that
    copy is returned with `stale=True`.

    A new 200 answer is kept only when `validate` (if given) accepts it: `validate` parses the
    answer and raises when it cannot. On a raise the previous copy stays in the cache and is
    returned with `stale=True`; with no previous copy the live answer is returned uncached.

    Each key is one file, `<sha256>.cache`: a JSON line of metadata, then the body. It is written
    to a temporary file and renamed into place, so a reader never sees half a file.
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

    def _load(self, key: str) -> Response | None:
        try:
            raw = (self._dir / f"{key}.cache").read_bytes()
            head, sep, body = raw.partition(b"\n")
            meta = jsonlib.loads(head)
            if not sep or not isinstance(meta, dict):
                return None
            stored_at = float(meta["stored_at"])
            content_type, url = meta["content_type"], meta["url"]
            if not isinstance(content_type, str) or not isinstance(url, str):
                return None
            return Response(200, body, content_type, url, stored_at=stored_at)
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _store(self, key: str, response: Response) -> None:
        meta = {
            "stored_at": self._clock(),
            "content_type": response.content_type,
            "url": response.url,
        }
        data = jsonlib.dumps(meta).encode() + b"\n" + response.content
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            handle, temp = tempfile.mkstemp(dir=self._dir, prefix=f"{key}.", suffix=".tmp")
            try:
                with os.fdopen(handle, "wb") as out:
                    out.write(data)
                os.replace(temp, self._dir / f"{key}.cache")
            except OSError:
                Path(temp).unlink(missing_ok=True)
                raise
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
        validate: Validate | None = None,
    ) -> Response:
        """Serve from cache when fresh, else ask the inner transport, falling back to stale."""
        if ttl is None:
            return self._inner.request(
                method, url, params=params, json=json, headers=headers, ttl=None
            )
        key = self._key(method, url, params, json)
        cached = self._load(key)
        if cached is not None and self._clock() - cached.stored_at < ttl:
            return cached
        try:
            live = self._inner.request(
                method, url, params=params, json=json, headers=headers, ttl=ttl
            )
        except TransportError:
            if cached is None:
                raise
            return replace(cached, stale=True)
        if (live.status >= 500 or live.status in STALE_ON) and cached is not None:
            return replace(cached, stale=True)
        if live.status == 200:
            if validate is not None:
                try:
                    validate(live)
                except Exception:  # any failure to parse means: do not keep it
                    return replace(cached, stale=True) if cached is not None else live
            self._store(key, live)
        return live
