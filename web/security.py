"""Local-only network guard for the FastHTML app (pure ASGI middleware).

The tool is a single-user, local, read-but-config-writing web app. Two protections
that Streamlit provided implicitly do NOT carry over to FastHTML/htmx and must be
added explicitly here:

  1. Bind to loopback so the app is not reachable from the LAN.
  2. Reject cross-site requests to the mutating routes (snapshot import, alias
     confirm, product-assign) so a page open in the user's browser can't drive
     the app via CSRF, and a rebound DNS name can't reach it.

This middleware is the enforcement layer; the bind is a launch flag (see below).
The middleware is defence-in-depth: even if the server is accidentally bound to
0.0.0.0, a request whose Host header is a LAN IP / attacker domain is refused.

Wiring (add both — one line each) when web/server.py is built:

    from starlette.middleware import Middleware
    from web.security import LocalOnlyMiddleware

    app, rt = fast_app(
        ...,
        middleware=[Middleware(LocalOnlyMiddleware)],
    )

and launch bound to loopback (uvicorn already defaults to 127.0.0.1; FastHTML's
serve() defaults to 0.0.0.0, so pass host explicitly if you use it):

    uvicorn web.server:app --host 127.0.0.1        # or:  serve(host="127.0.0.1")

Pure ASGI (no framework-version coupling): usable via Middleware(...),
app.add_middleware(LocalOnlyMiddleware), or by wrapping the ASGI app directly.
"""

from __future__ import annotations

from urllib.parse import urlsplit

# Hostnames that count as "this machine". Ports are ignored in the comparison.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# Methods that change server state (config writes, snapshot import). Only these
# require a same-origin check; GET/HEAD navigation and downloads are exempt.
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _hostname(value: str) -> str | None:
    """Extract the hostname from a Host header (``h:port``, ``[::1]:port``) or a
    full origin/referer URL. Returns None if it can't be parsed."""
    if not value:
        return None
    value = value.strip()
    parsed = urlsplit(value if "://" in value else "//" + value)
    return parsed.hostname  # lower-cased, brackets stripped for IPv6, port dropped


class LocalOnlyMiddleware:
    """Refuse any request that isn't addressed to (Host) and, for state changes,
    originated from (Origin/Referer) this machine over loopback."""

    def __init__(self, app, allowed_hosts: frozenset[str] = LOOPBACK_HOSTS):
        self.app = app
        self.allowed_hosts = allowed_hosts

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)  # lifespan/websocket: pass through
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}

        # 1. Host must be loopback — blocks LAN access and DNS-rebinding, since a
        #    rebound name or LAN IP arrives in the Host header, not 127.0.0.1.
        if _hostname(headers.get("host", "")) not in self.allowed_hosts:
            await self._deny(send, "Host header is not a local address.")
            return

        # 2. State-changing requests must be same-origin — blocks CSRF from any
        #    other site the browser has open. Browsers always send Origin on these
        #    methods; absence is treated as untrusted.
        if scope["method"] in MUTATING_METHODS:
            source = headers.get("origin") or headers.get("referer")
            if _hostname(source or "") not in self.allowed_hosts:
                await self._deny(send, "Cross-site request rejected.")
                return

        await self.app(scope, receive, send)

    @staticmethod
    async def _deny(send, reason: str) -> None:
        await send({
            "type": "http.response.start",
            "status": 403,
            "headers": [(b"content-type", b"text/plain; charset=utf-8")],
        })
        await send({"type": "http.response.body", "body": reason.encode("utf-8")})
