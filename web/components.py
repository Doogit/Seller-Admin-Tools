"""Shared FastHTML layout + presentational components (mirrors app/ui.py's role
for Streamlit, but purely structural — no numbers/strings are generated here;
those come from core/views/*). Built with tool 1 and reused by tools 2-3."""

from __future__ import annotations

from fasthtml.common import (
    A, Div, H1, H2, Header, Li, Main, Nav, P, Span, Table, Tbody, Td, Th, Thead,
    Title, Tr, Ul,
)

APP_NAME = "Seller Admin Tools"

# (label, path, blurb). Paths are the per-tool routes.
TOOLS = (
    ("Pipeline Import", "/home",
     "Upload a pipeline CSV, map columns, save a snapshot."),
    ("Forecast Narrative", "/forecast-narrative",
     "Weekly commit / upside / risk narrative draft."),
    ("QBR Assembler", "/qbr",
     "Quarterly business review deck (.pptx / .md)."),
    ("Account Plan", "/account-plan",
     "Account plan with account-facts import."),
)


def page(title: str, *content, active: str | None = None):
    """Full-page wrapper. fast_app injects the vendored htmx/fasthtml.js/Tailwind
    headers; returning a Title sets the document title. `active` highlights the
    current tool in the nav."""
    return (
        Title(f"{title} — {APP_NAME}"),
        Header(
            Div(
                A(APP_NAME, href="/",
                  cls="text-lg font-semibold text-ink hover:text-brand"),
                Nav(
                    *(A(label, href=path,
                        cls=("px-2 py-1 rounded text-sm "
                             + ("bg-brand text-white"
                                if active == path
                                else "text-muted hover:text-ink hover:bg-bg")))
                      for label, path, _ in TOOLS),
                    cls="flex gap-2",
                ),
                cls="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between",
            ),
            cls="border-b border-border bg-surface",
        ),
        Main(*content, cls="max-w-5xl mx-auto px-4 py-8"),
    )


def tool_card(label: str, path: str, blurb: str):
    return A(
        H2(label, cls="text-base font-semibold text-ink"),
        P(blurb, cls="mt-1 text-sm text-muted"),
        href=path,
        cls=("block rounded-lg border border-border bg-surface p-5 "
             "hover:border-brand hover:shadow-sm transition"),
    )


def _delta(delta: str):
    """Week-over-week delta with a direction glyph + status tone. Deltas only
    appear on Commit/Upside, where an increase is a gain (positive token); a
    decrease reads in the high token. Parses the pre-formatted money string."""
    if delta == "$0":
        return P(delta, cls="mt-1 text-xs text-muted tabular-nums")
    down = delta.lstrip().startswith("-")
    glyph, tone = ("▼", "text-high-ink") if down else ("▲", "text-positive-ink")
    return P(f"{glyph} {delta}",
             cls=f"mt-1 text-xs font-medium tabular-nums {tone}")


def _metric_card(label: str, value: str, delta: str | None = None,
                 attn: bool = False):
    val_tone = "text-high" if attn else "text-ink"
    top = " border-t-2 border-high" if attn else ""
    return Div(
        P(label, cls="text-xs font-semibold uppercase tracking-wide text-muted"),
        P(value, cls=f"mt-1 text-2xl font-semibold tabular-nums {val_tone}"),
        (_delta(delta) if delta else ""),
        cls=f"rounded-lg border border-border bg-surface p-4{top}",
    )


def metric_cards(metrics: dict):
    """Commit / Upside / Coverage / At-risk cards + derived/unclassified notes.
    Shared by the Forecast Narrative and QBR scorecards (identical strings, from
    core.views.common.metric_block). At-risk carries the high token — it's the
    exposure number to read first. The derived note gets a medium stripe."""
    cards = Div(
        _metric_card("Commit", metrics["commit"], metrics["commit_delta"]),
        _metric_card("Upside", metrics["upside"], metrics["upside_delta"]),
        _metric_card("Coverage", metrics["coverage"]),
        _metric_card("At risk", metrics["at_risk"], attn=True),
        cls="grid gap-3 sm:grid-cols-4",
    )
    notes = [P(n, cls="mt-2 border-l-2 border-medium pl-2 text-xs text-muted")
             for n in (metrics["derived_note"], metrics["unclassified_note"]) if n]
    return Div(cards, *notes)


# Okabe-Ito status tones -> (dot, tint background, ink text) utility classes.
# Literal strings so Tailwind's content scan tree-shakes them (no interpolation).
_CHIP_TONES = {
    "high": ("bg-high", "bg-high-tint", "text-high-ink"),
    "medium": ("bg-medium", "bg-medium-tint", "text-medium-ink"),
    "positive": ("bg-positive", "bg-positive-tint", "text-positive-ink"),
}


def _chip(text: str, tone: str = "high"):
    """Status chip: tinted background + a colored dot + the literal status word,
    so meaning is never carried by color alone (colorblind-safe). `tone` selects
    the Okabe-Ito status color; it defaults to high — the risk/exception tables,
    where every row is a genuine risk flag."""
    dot, tint, ink = _CHIP_TONES.get(tone, _CHIP_TONES["high"])
    return Span(
        Span(cls=f"mr-1.5 inline-block h-1.5 w-1.5 rounded-sm {dot}"),
        text,
        cls=f"inline-flex items-center rounded-full {tint} px-2 py-0.5 "
            f"text-xs font-semibold {ink}",
    )


def _is_numeric(val: str) -> bool:
    s = str(val).strip()
    return bool(s) and (s[0] == "$" or s.lstrip("-").replace(",", "").isdigit())


def data_table(columns, rows, empty_text: str | None = None,
               chip_col: str | None = None, chip_tone: dict | None = None):
    """Generic read-only table from view-model columns + row dicts. Rows are
    pre-formatted in the view model (amounts money-formatted). Scrolls
    horizontally on narrow screens; never overflows the page.

    Money/count columns right-align with tabular figures so magnitudes compare
    down the column; the optional chip_col renders its value as a status chip
    (used by the risk/exception tables). chip_tone optionally maps a cell value
    to an Okabe-Ito tone (else every chip is high). No view-model string is
    altered."""
    if not rows:
        return P(empty_text or "", cls="text-sm text-muted")
    numeric = {c: any(_is_numeric(r.get(c, "")) for r in rows) for c in columns}

    def _th(c):
        align = "text-right" if numeric[c] else "text-left"
        return Th(c.replace("_", " "),
                  cls=(f"px-3 py-2 {align} text-xs font-semibold uppercase "
                       "tracking-wide text-muted"))

    def _td(c, r):
        if chip_col and c == chip_col:
            val = str(r.get(c, ""))
            return Td(_chip(val, (chip_tone or {}).get(val, "high")),
                      cls="px-3 py-2 align-top")
        align = " text-right tabular-nums" if numeric[c] else ""
        return Td(str(r.get(c, "")), cls=f"px-3 py-2 align-top{align}")

    head = Thead(Tr(*(_th(c) for c in columns),
                    cls="border-b border-border bg-surface"))
    body = Tbody(*(Tr(*(_td(c, r) for c in columns),
                      cls="odd:bg-surface even:bg-bg")
                   for r in rows))
    return Div(Table(head, body, cls="w-full text-sm"),
               cls="overflow-x-auto rounded-lg border border-border bg-surface")


def landing():
    return page(
        "Home",
        H1("Seller admin tools", cls="text-2xl font-bold text-ink"),
        P("Local, offline, read-only. Turn a weekly pipeline snapshot into "
          "admin artifacts.", cls="mt-1 text-muted"),
        Div(*(tool_card(*t) for t in TOOLS),
            cls="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4"),
    )
