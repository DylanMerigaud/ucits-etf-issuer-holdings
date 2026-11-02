from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from ucits_etf_issuer_holdings import __version__
from ucits_etf_issuer_holdings.errors import TransportError
from ucits_etf_issuer_holdings.http import CachingTransport, HttpxTransport, Response, Transport


def test_response_text_and_json() -> None:
    resp = Response(200, b'{"a": 1}', "application/json", "https://x")
    assert resp.text == '{"a": 1}'
    assert resp.json() == {"a": 1}
    assert resp.stale is False


def test_httpx_transport_sends_user_agent_and_params() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True}, headers={"content-type": "application/json"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = HttpxTransport(client=client)
    resp = transport.request(
        "GET", "https://example.com/a", params={"x": "1"}, headers={"Origin": "https://o"}
    )
    assert resp.status == 200
    assert resp.json() == {"ok": True}
    assert resp.content_type == "application/json"
    request = seen[0]
    assert request.headers["user-agent"].startswith(
        f"ucits-etf-issuer-holdings/{__version__} (+https://github.com/"
    )
    assert request.headers["origin"] == "https://o"
    assert request.url.params["x"] == "1"


def test_httpx_transport_posts_json() -> None:
    bodies: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(200, text="done")

    transport = HttpxTransport(client=httpx.Client(transport=httpx.MockTransport(handler)))
    transport.request("POST", "https://example.com/p", json={"k": [1, 2]})
    assert b'"k"' in bodies[0]


def test_httpx_transport_wraps_network_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    transport = HttpxTransport(client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(TransportError):
        transport.request("GET", "https://example.com/")


class FakeTransport:
    """Counts calls and answers from a script of Response or Exception items."""

    def __init__(self, script: list[Response | Exception]) -> None:
        self.script = list(script)
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
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def ok(body: str = "hello") -> Response:
    return Response(200, body.encode(), "text/plain", "https://x/a")


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_caching_returns_fresh_copy_without_request(tmp_path: Path) -> None:
    inner = FakeTransport([ok("one")])
    cache = CachingTransport(inner, tmp_path)
    first = cache.request("GET", "https://x/a", params={"b": "2", "a": "1"}, ttl=60)
    second = cache.request("GET", "https://x/a", params={"a": "1", "b": "2"}, ttl=60)
    assert first.text == second.text == "one"
    assert inner.calls == 1
    assert second.content_type == "text/plain"
    assert second.stale is False


def test_caching_ttl_none_never_caches(tmp_path: Path) -> None:
    inner = FakeTransport([ok("one"), ok("two")])
    cache = CachingTransport(inner, tmp_path)
    cache.request("GET", "https://x/a")
    assert cache.request("GET", "https://x/a").text == "two"
    assert not list(tmp_path.iterdir())


def test_caching_expired_copy_is_refetched(tmp_path: Path) -> None:
    clock = Clock()
    inner = FakeTransport([ok("one"), ok("two")])
    cache = CachingTransport(inner, tmp_path, clock=clock)
    cache.request("GET", "https://x/a", ttl=60)
    clock.now += 61
    assert cache.request("GET", "https://x/a", ttl=60).text == "two"


def test_caching_post_key_uses_canonical_json(tmp_path: Path) -> None:
    inner = FakeTransport([ok("one"), ok("two")])
    cache = CachingTransport(inner, tmp_path)
    cache.request("POST", "https://x/p", json={"a": 1, "b": 2}, ttl=60)
    assert cache.request("POST", "https://x/p", json={"b": 2, "a": 1}, ttl=60).text == "one"
    assert cache.request("POST", "https://x/p", json={"a": 1, "b": 3}, ttl=60).text == "two"


def test_caching_only_stores_200(tmp_path: Path) -> None:
    inner = FakeTransport([Response(404, b"no", "text/plain", "u"), ok("yes")])
    cache = CachingTransport(inner, tmp_path)
    assert cache.request("GET", "https://x/a", ttl=60).status == 404
    assert cache.request("GET", "https://x/a", ttl=60).text == "yes"


def test_stale_copy_on_transport_error(tmp_path: Path) -> None:
    clock = Clock()
    inner = FakeTransport([ok("old"), TransportError("down")])
    cache = CachingTransport(inner, tmp_path, clock=clock)
    cache.request("GET", "https://x/a", ttl=60)
    clock.now += 600
    resp = cache.request("GET", "https://x/a", ttl=60)
    assert resp.text == "old"
    assert resp.stale is True


def test_stale_copy_on_server_error(tmp_path: Path) -> None:
    clock = Clock()
    inner = FakeTransport([ok("old"), Response(503, b"x", "text/plain", "u")])
    cache = CachingTransport(inner, tmp_path, clock=clock)
    cache.request("GET", "https://x/a", ttl=60)
    clock.now += 600
    resp = cache.request("GET", "https://x/a", ttl=60)
    assert (resp.text, resp.stale) == ("old", True)


def test_no_stale_copy_means_the_error_propagates(tmp_path: Path) -> None:
    cache = CachingTransport(FakeTransport([TransportError("down")]), tmp_path)
    with pytest.raises(TransportError):
        cache.request("GET", "https://x/a", ttl=60)
    cache = CachingTransport(FakeTransport([Response(500, b"x", "text/plain", "u")]), tmp_path)
    assert cache.request("GET", "https://x/b", ttl=60).status == 500


def test_protocol_is_satisfied() -> None:
    transport: Transport = FakeTransport([])
    assert transport is not None
