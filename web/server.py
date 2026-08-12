"""FastHTML ASGI app: offline-first skeleton for the ported tool pages.

Offline is the #1 risk (see docs/fasthtml-port-plan.md, Task 0). fast_app injects
five CDN assets by default (htmx, fasthtml.js, surreal, css-scope-inline, a Pico
fork); we disable all of them (default_hdrs=False, pico=False) and serve local
copies from web/static/. The startup assert below fails fast if any external
header URL ever reappears.

Run: uvicorn web.server:app --reload   (styles: make css)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fasthtml.common import (  # noqa: E402
    Link, Meta, Script, fast_app, serve, to_xml,
)

from web.components import landing  # noqa: E402
from web.routes import account_plan, forecast_narrative, qbr  # noqa: E402

STATIC_DIR = REPO_ROOT / "web" / "static"

app, rt = fast_app(
    pico=False,             # suppress the third-party Pico CDN fork
    default_hdrs=False,     # suppress htmx/fasthtml.js/surreal/scope-inline CDN + default meta
    static_path=str(STATIC_DIR),
    hdrs=(
        Meta(charset="utf-8"),
        Meta(name="viewport", content="width=device-width, initial-scale=1"),
        Script(src="/htmx.min.js"),   # vendored htmx 2.0.7
        Script(src="/fasthtml.js"),   # vendored fasthtml-js 1.0.12 (OOB/boost conveniences)
        Link(rel="stylesheet", href="/tailwind.css"),
    ),
)

# Startup assert: no header may reference an external origin (offline guarantee).
_EXTERNAL = re.compile(r'(?:src|href)\s*=\s*["\']https?://', re.I)
for _h in app.hdrs:
    _xml = to_xml(_h)
    if _EXTERNAL.search(_xml):
        raise RuntimeError(f"External header URL detected (offline invariant broken): {_xml}")


@rt("/")
def index():
    return landing()


forecast_narrative.register(rt)
qbr.register(rt)
account_plan.register(rt)


if __name__ == "__main__":
    serve()
