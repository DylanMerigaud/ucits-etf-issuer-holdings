from __future__ import annotations

import time
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


@pytest.mark.parametrize("status", [403, 408, 429, 500, 503])
def test_stale_copy_on_refusal_timeout_rate_limit_and_server_error(
    tmp_path: Path, status: int
) -> None:
    clock = Clock()
    inner = FakeTransport([ok("old"), Response(status, b"x", "text/plain", "u")])
    cache = CachingTransport(inner, tmp_path, clock=clock)
    cache.request("GET", "https://x/a", ttl=60)
    clock.now += 600
    resp = cache.request("GET", "https://x/a", ttl=60)
    assert (resp.text, resp.stale) == ("old", True)


def test_no_stale_copy_on_404(tmp_path: Path) -> None:
    clock = Clock()
    inner = FakeTransport([ok("old"), Response(404, b"gone", "text/plain", "u")])
    cache = CachingTransport(inner, tmp_path, clock=clock)
    cache.request("GET", "https://x/a", ttl=60)
    clock.now += 600
    assert cache.request("GET", "https://x/a", ttl=60).status == 404


def reject_bad(response: Response) -> None:
    if response.text == "bad":
        raise ValueError("cannot parse")


def test_answer_the_validator_rejects_is_not_cached(tmp_path: Path) -> None:
    clock = Clock()
    inner = FakeTransport([ok("good"), ok("bad"), ok("good again")])
    cache = CachingTransport(inner, tmp_path, clock=clock)
    cache.request("GET", "https://x/a", ttl=60, validate=reject_bad)
    clock.now += 600
    served = cache.request("GET", "https://x/a", ttl=60, validate=reject_bad)
    assert (served.text, served.stale) == ("good", True)
    assert served.stored_at == 1000.0
    # the previous copy is still the one on disk, and still expired: the next call asks again
    assert cache.request("GET", "https://x/a", ttl=60, validate=reject_bad).text == "good again"
    assert inner.calls == 3


def test_rejected_answer_without_previous_copy_is_returned_uncached(tmp_path: Path) -> None:
    inner = FakeTransport([ok("bad"), ok("bad")])
    cache = CachingTransport(inner, tmp_path)
    first = cache.request("GET", "https://x/a", ttl=60, validate=reject_bad)
    assert (first.text, first.stale) == ("bad", False)
    cache.request("GET", "https://x/a", ttl=60, validate=reject_bad)
    assert inner.calls == 2
    assert not list(tmp_path.glob("*.cache"))


def test_one_file_per_key_and_no_temp_left(tmp_path: Path) -> None:
    cache = CachingTransport(FakeTransport([ok("one")]), tmp_path)
    cache.request("GET", "https://x/a", ttl=60)
    names = [p.name for p in tmp_path.iterdir()]
    assert len(names) == 1 and names[0].endswith(".cache")


def test_a_corrupt_cache_file_is_a_miss(tmp_path: Path) -> None:
    clock = Clock()
    inner = FakeTransport([ok("one"), ok("two")])
    cache = CachingTransport(inner, tmp_path, clock=clock)
    cache.request("GET", "https://x/a", ttl=60)
    (path,) = tmp_path.glob("*.cache")
    path.write_bytes(b"not json at all")
    assert cache.request("GET", "https://x/a", ttl=60).text == "two"


def test_stored_at_is_the_store_time_for_a_cached_copy(tmp_path: Path) -> None:
    clock = Clock()
    cache = CachingTransport(FakeTransport([ok("one")]), tmp_path, clock=clock)
    cache.request("GET", "https://x/a", ttl=60)
    clock.now += 30
    assert cache.request("GET", "https://x/a", ttl=60).stored_at == 1000.0


def test_live_response_stored_at_is_now() -> None:
    before = time.time()
    assert Response(200, b"", "t", "u").stored_at >= before


def test_httpx_transport_closes_only_its_own_client() -> None:
    own = HttpxTransport()
    own.close()
    assert own._client.is_closed
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    HttpxTransport(client=client).close()
    assert not client.is_closed
