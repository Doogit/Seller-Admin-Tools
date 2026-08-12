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
                  cls="text-lg font-semibold text-slate-900 hover:text-slate-700"),
                Nav(
                    *(A(label, href=path,
                        cls=("px-2 py-1 rounded text-sm "
                             + ("bg-slate-900 text-white"
                                if active == path
                                else "text-slate-600 hover:text-slate-900")))
                      for label, path, _ in TOOLS),
                    cls="flex gap-2",
                ),
                cls="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between",
            ),
            cls="border-b border-slate-200 bg-white",
        ),
        Main(*content, cls="max-w-5xl mx-auto px-4 py-8"),
    )


def tool_card(label: str, path: str, blurb: str):
    return A(
        H2(label, cls="text-base font-semibold text-slate-900"),
        P(blurb, cls="mt-1 text-sm text-slate-600"),
        href=path,
        cls=("block rounded-lg border border-slate-200 bg-white p-5 "
             "hover:border-slate-400 hover:shadow-sm transition"),
    )


def _metric_card(label: str, value: str, delta: str | None = None):
    return Div(
        P(label, cls="text-xs font-medium text-slate-500"),
        P(value, cls="mt-1 text-xl font-semibold text-slate-900"),
        (P(delta, cls="text-xs text-slate-500") if delta else ""),
        cls="rounded-lg border border-slate-200 bg-white p-4",
    )


def metric_cards(metrics: dict):
    """Commit / Upside / Coverage / At-risk cards + derived/unclassified notes.
    Shared by the Forecast Narrative and QBR scorecards (identical strings, from
    core.views.common.metric_block)."""
    cards = Div(
        _metric_card("Commit", metrics["commit"], metrics["commit_delta"]),
        _metric_card("Upside", metrics["upside"], metrics["upside_delta"]),
        _metric_card("Coverage", metrics["coverage"]),
        _metric_card("At risk", metrics["at_risk"]),
        cls="grid gap-3 sm:grid-cols-4",
    )
    notes = [P(n, cls="mt-2 text-xs text-slate-500")
             for n in (metrics["derived_note"], metrics["unclassified_note"]) if n]
    return Div(cards, *notes)


def data_table(columns, rows, empty_text: str | None = None):
    """Generic read-only table from view-model columns + row dicts. Rows are
    pre-formatted in the view model (amounts money-formatted). Scrolls
    horizontally on narrow screens; never overflows the page."""
    if not rows:
        return P(empty_text or "", cls="text-sm text-slate-600")
    head = Thead(Tr(*(Th(c.replace("_", " "),
                         cls="px-2 py-1 text-left font-medium text-slate-600")
                      for c in columns)))
    body = Tbody(*(Tr(*(Td(str(r.get(c, "")), cls="px-2 py-1 align-top")
                        for c in columns),
                      cls="border-t border-slate-100")
                   for r in rows))
    return Div(Table(head, body, cls="w-full text-sm"),
               cls="overflow-x-auto rounded border border-slate-200")


def landing():
    return page(
        "Home",
        H1("Seller admin tools", cls="text-2xl font-bold text-slate-900"),
        P("Local, offline, read-only. Turn a weekly pipeline snapshot into "
          "admin artifacts.", cls="mt-1 text-slate-600"),
        Div(*(tool_card(*t) for t in TOOLS),
            cls="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4"),
    )
