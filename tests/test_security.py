"""LocalOnlyMiddleware: loopback Host + same-origin mutating requests.

Pure-ASGI tests — no TestClient/httpx dependency, no event loop plugin. Each
case drives the middleware directly with a crafted scope and captures the status.
"""

from __future__ import annotations

import asyncio

from web.security import LocalOnlyMiddleware

OK_HOST = "127.0.0.1:5001"
OK_ORIGIN = "http://127.0.0.1:5001"


async def _inner_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _status(method: str = "GET", host: str = OK_HOST, headers: dict | None = None) -> int:
    raw = [(b"host", host.encode())]
    for k, v in (headers or {}).items():
        raw.append((k.encode(), v.encode()))
    scope = {"type": "http", "method": method, "path": "/", "headers": raw}
    sent: list[dict] = []

    async def send(msg):
        sent.append(msg)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    asyncio.run(LocalOnlyMiddleware(_inner_app)(scope, receive, send))
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


def test_get_from_loopback_allowed():
    assert _status("GET", host=OK_HOST) == 200


def test_get_ipv6_loopback_allowed():
    assert _status("GET", host="[::1]:5001") == 200


def test_get_from_lan_host_blocked():
    # DNS-rebinding / direct LAN hit: the attacker name/IP rides in the Host header.
    assert _status("GET", host="192.168.1.20:5001") == 403
    assert _status("GET", host="evil.example.com") == 403


def test_post_same_origin_allowed():
    assert _status("POST", host=OK_HOST, headers={"origin": OK_ORIGIN}) == 200


def test_post_cross_site_origin_blocked():
    assert _status("POST", host=OK_HOST, headers={"origin": "http://evil.example.com"}) == 403


def test_post_without_origin_blocked():
    # Browsers send Origin on state-changing requests; its absence is untrusted.
    assert _status("POST", host=OK_HOST) == 403


def test_post_falls_back_to_referer():
    assert _status("POST", host=OK_HOST, headers={"referer": "http://localhost:5001/x"}) == 200
