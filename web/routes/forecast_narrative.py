"""Tool 1 route — Forecast Narrative. Renders strictly from the view model
(core/views/forecast_narrative.py); no user-facing string is built here except
static structural labels. Interaction contract: docs/fasthtml-port-plan.md §C.

Regions (htmx targets):
  #tool-body — everything below H1. Snapshot / Compare change swaps the WHOLE
               body (regenerates the draft — snapshot-keyed numbers, discards
               edits by design).
  #metrics   — Commit/Upside/Coverage/At-risk cards. A Quota change swaps ONLY
               this, leaving the draft textarea (outside the target) untouched
               → edits preserved.
  #draft     — the three editable sections + Regenerate + export. Regenerate is
               a dirty-guarded POST (see web/static/forecast_narrative.js).
"""

from __future__ import annotations

from fasthtml.common import (
    Button, Details, Div, Form, H1, H2, Input, Label, Option, P, Pre, Script,
    Select, Span, Summary, Textarea,
)
from starlette.responses import Response

from core.views import forecast_narrative as vm
from web.components import data_table, metric_cards, page
from web.routes import _params

BASE = "/forecast-narrative"


# --- fragments ---------------------------------------------------------------

_SEL = ("block w-full rounded border border-border px-2 py-1 text-sm "
        "focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand")


def _controls(v: vm.ForecastView):
    snap = Div(
        Label("Snapshot", fr="current_id",
              cls="block text-xs font-medium text-muted"),
        Select(
            *(Option(lbl, value=str(sid), selected=(sid == v.current_id))
              for sid, lbl in v.snapshot_options),
            id="current_id", name="current_id", cls=_SEL,
            hx_get=f"{BASE}/body", hx_target="#tool-body", hx_swap="outerHTML",
            hx_include="#controls",
        ),
    )
    compare = Div(
        Label("Compare against", fr="prior_id",
              cls="block text-xs font-medium text-muted"),
        Select(
            Option(vm.PRIOR_NONE_LABEL, value="", selected=(v.prior_id is None)),
            *(Option(lbl, value=str(sid), selected=(sid == v.prior_id))
              for sid, lbl in v.prior_options),
            id="prior_id", name="prior_id", cls=_SEL,
            hx_get=f"{BASE}/body", hx_target="#tool-body", hx_swap="outerHTML",
            hx_include="#controls",
        ),
    )
    quota = Div(
        Label("Quota (optional, session-only)", fr="quota",
              cls="block text-xs font-medium text-muted"),
        Input(
            type="number", id="quota", name="quota", min="0", step="100000",
            value=("" if not v.quota else f"{v.quota:.0f}"), cls=_SEL,
            hx_get=f"{BASE}/metrics", hx_target="#metrics", hx_swap="outerHTML",
            hx_include="#controls",
        ),
    )
    return Form(
        Div(snap, compare, quota, cls="grid gap-3 sm:grid-cols-3"),
        id="controls",
    )


def _metrics(v: vm.ForecastView):
    warn = ([Div(v.unmatched["warning"],
                 cls="mt-3 rounded-md border-l-4 border-medium bg-medium-tint "
                     "px-3 py-2 text-sm text-medium-ink", role="status")]
            if v.unmatched["warning"] else [])
    return Div(metric_cards(v.metrics), *warn, id="metrics")


def _draft_inner(v: vm.ForecastView):
    export_md = vm.export_markdown(v.draft, v.period)
    fields = [
        Div(
            Label(vm.SECTION_LABELS[s], fr=f"ta-{s}",
                  cls="block text-sm font-medium text-ink"),
            Textarea(v.draft[s], id=f"ta-{s}", name=s, rows="4",
                     cls="mt-1 block w-full rounded border border-border "
                         "px-2 py-1 text-sm font-mono focus:border-brand "
                         "focus:outline-none focus:ring-1 focus:ring-brand",
                     **{"data-generated": v.draft[s]}),
            cls="mt-3",
        )
        for s in vm.SECTIONS
    ]
    draft_form = Form(
        Input(type="hidden", name="current_id", value=str(v.current_id)),
        Input(type="hidden", name="prior_id",
              value=("" if v.prior_id is None else str(v.prior_id))),
        Input(type="hidden", name="quota",
              value=("" if not v.quota else f"{v.quota:.0f}")),
        *fields,
        Div(
            Button("Regenerate", type="button",
                   hx_post=f"{BASE}/draft", hx_target="#draft", hx_swap="innerHTML",
                   hx_include="#controls",
                   hx_sync="this:drop", hx_disabled_elt="this",
                   hx_indicator="#draft-spin",
                   **{"data-confirm-dirty": "1"},
                   cls="rounded bg-brand px-3 py-1.5 text-sm font-medium "
                       "text-white hover:bg-brand-dark disabled:opacity-50"),
            Span("regenerating…", id="draft-spin",
                 cls="htmx-indicator ml-2 text-xs text-muted"),
            Button("Download .md", type="submit",
                   formaction=f"{BASE}/export", formmethod="post",
                   cls="ml-2 rounded border border-border px-3 py-1.5 text-sm "
                       "font-medium text-ink hover:bg-bg"),
            cls="mt-3 flex items-center",
        ),
        id="draft-form",
    )
    return [
        H2("Draft — review before submitting",
           cls="text-base font-semibold text-ink"),
        draft_form,
        H2("Export", cls="mt-6 text-base font-semibold text-ink"),
        Pre(export_md,
            cls="mt-2 overflow-x-auto rounded border border-border bg-surface p-3 text-xs "
                "text-ink whitespace-pre-wrap"),
    ]


def _draft(v: vm.ForecastView):
    return Div(*_draft_inner(v), id="draft")


def _challenge(v: vm.ForecastView):
    c = v.challenge
    return Div(
        H2("Largest open deals (challenge list)",
           cls="mt-6 text-base font-semibold text-ink"),
        P("Top open deals by amount — the commit/upside deals to pressure-test on "
          "the call. The flags column shows which already tripped a risk rule.",
          cls="text-xs text-muted"),
        Div(data_table(c["columns"], c["rows"]), cls="mt-2"),
    )


def _risk(v: vm.ForecastView):
    r = v.risk
    return Div(
        H2("Risk detail (coaching view)",
           cls="mt-6 text-base font-semibold text-ink"),
        *[P(n, cls="text-xs text-muted") for n in r["notes"]],
        data_table(r["columns"], r["rows"], r["empty_text"], chip_col="rule"),
    )


def _movement(v: vm.ForecastView):
    mv = v.movement
    if not mv["rows"]:
        return ""
    return Details(
        Summary("Week-over-week movement detail",
                cls="cursor-pointer text-sm font-medium text-ink"),
        Div(data_table(mv["columns"], mv["rows"]), cls="mt-2"),
        cls="mt-4",
    )


def _footer():
    return P(vm.FOOTER, cls="mt-8 border-t border-border pt-3 text-xs text-muted")


def _body(v: vm.ForecastView):
    return Div(
        _controls(v), Div(_metrics(v), cls="mt-4"), Div(_draft(v), cls="mt-6"),
        _challenge(v), _risk(v), _movement(v), _footer(),
        id="tool-body",
    )


def _full_page(v: vm.ForecastView):
    return page(
        "Forecast Narrative",
        H1("Forecast narrative", cls="text-2xl font-bold text-ink"),
        _body(v),
        Script(src="/forecast_narrative.js"),
        active=BASE,
    )


def _empty_page():
    return page(
        "Forecast Narrative",
        H1("Forecast narrative", cls="text-2xl font-bold text-ink"),
        P(vm.EMPTY_STATE, cls="mt-4 rounded border border-border bg-surface "
                              "px-4 py-3 text-muted"),
        active=BASE,
    )


# --- registration ------------------------------------------------------------

def register(rt):
    @rt(BASE)
    def get(current_id: str = None, prior_id: str = None, quota: str = None):
        options = vm.snapshot_options()
        if not options:
            return _empty_page()
        cid, pid = _params.resolve(_params.cid(current_id), _params.pid(prior_id), options)
        return _full_page(vm.build(cid, pid, _params.quota(quota)))

    @rt(f"{BASE}/body")
    def get(current_id: str = None, prior_id: str = None, quota: str = None):
        options = vm.snapshot_options()
        cid, pid = _params.resolve(_params.cid(current_id), _params.pid(prior_id), options)
        return _body(vm.build(cid, pid, _params.quota(quota)))

    @rt(f"{BASE}/metrics")
    def get(current_id: str = None, prior_id: str = None, quota: str = None):
        options = vm.snapshot_options()
        cid, pid = _params.resolve(_params.cid(current_id), _params.pid(prior_id), options)
        return _metrics(vm.build(cid, pid, _params.quota(quota)))

    @rt(f"{BASE}/draft", methods=["post"])
    def post(current_id: str = None, prior_id: str = None, quota: str = None):
        options = vm.snapshot_options()
        cid, pid = _params.resolve(_params.cid(current_id), _params.pid(prior_id), options)
        return _draft_inner(vm.build(cid, pid, _params.quota(quota)))

    @rt(f"{BASE}/export", methods=["post"])
    def post(commit: str = "", upside: str = "", risk: str = "",
             current_id: str = None):
        cid = _params.cid(current_id)
        period = vm.period_for(cid) if cid is not None else ""
        md = vm.export_markdown(
            {"commit": commit, "upside": upside, "risk": risk}, period)
        return Response(
            md, media_type="text/markdown",
            headers={"Content-Disposition": 'attachment; filename="forecast_narrative.md"'},
        )
