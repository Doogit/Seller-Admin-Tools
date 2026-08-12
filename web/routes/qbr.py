"""Tool 2 route — QBR Assembler. Renders strictly from the view model
(core/views/qbr.py); the .pptx/.md downloads stream core.deck bytes unchanged.

Interaction (inventory §C): no editable draft, so the controls form (#qbr-controls)
is static (typed Period/Team survive). Snapshot / Prior / Quota change swaps only
#qbr-data (metrics, chart, tables, downloads). Downloads are read-only GET form
submits carrying all control values; the filename is stamped with today's date.
"""

from __future__ import annotations

import datetime as dt

from fasthtml.common import (
    Button, Div, Form, H1, H2, Input, Label, Option, P, Select,
)
from starlette.responses import Response

from core import deck
from core.views import qbr as vm
from web.components import data_table, metric_cards, page
from web.routes import _params

BASE = "/qbr"
CHART_EMPTY = "No open pipeline to chart in this snapshot."

_SEL = "block w-full rounded border border-slate-300 px-2 py-1 text-sm"
_LBL = "block text-xs font-medium text-slate-600"


# --- fragments ---------------------------------------------------------------

def _controls(v: vm.QbrView):
    return Form(
        Div(
            Div(Label("Snapshot", fr="current_id", cls=_LBL),
                Select(*(Option(lbl, value=str(sid), selected=(sid == v.current_id))
                         for sid, lbl in v.snapshot_options),
                       id="current_id", name="current_id", cls=_SEL,
                       hx_get=f"{BASE}/body", hx_target="#qbr-data",
                       hx_swap="outerHTML", hx_include="#qbr-controls")),
            Div(Label("Prior snapshot", fr="prior_id", cls=_LBL),
                Select(Option(vm.PRIOR_NONE_LABEL, value="", selected=(v.prior_id is None)),
                       *(Option(lbl, value=str(sid), selected=(sid == v.prior_id))
                         for sid, lbl in v.prior_options),
                       id="prior_id", name="prior_id", cls=_SEL,
                       hx_get=f"{BASE}/body", hx_target="#qbr-data",
                       hx_swap="outerHTML", hx_include="#qbr-controls")),
            Div(Label("Period label", fr="period", cls=_LBL),
                Input(type="text", id="period", name="period", value=v.period, cls=_SEL)),
            Div(Label("Team / segment", fr="team", cls=_LBL),
                Input(type="text", id="team", name="team", value=v.team, cls=_SEL)),
            Div(Label("Quota (optional)", fr="quota", cls=_LBL),
                Input(type="number", id="quota", name="quota", min="0", step="100000",
                      value=("" if not v.quota else f"{v.quota:.0f}"), cls=_SEL,
                      hx_get=f"{BASE}/body", hx_target="#qbr-data",
                      hx_swap="outerHTML", hx_include="#qbr-controls")),
            cls="grid gap-3 sm:grid-cols-5",
        ),
        id="qbr-controls",
    )


def _chart(v: vm.QbrView):
    if v.stage["empty"]:
        return P(CHART_EMPTY, cls="text-sm text-slate-600")
    rows = [
        Div(
            Div(P(b["bucket"], cls="text-xs text-slate-600"),
                cls="w-24 shrink-0"),
            Div(
                Div(cls="h-4 rounded bg-slate-800", style=f"width: {max(b['pct'], 2)}%"),
                cls="flex-1",
            ),
            Div(P(b["amount_str"], cls="text-xs tabular-nums text-slate-700"),
                cls="w-16 shrink-0 text-right"),
            cls="flex items-center gap-2",
        )
        for b in v.stage["bars"]
    ]
    return Div(*rows, cls="space-y-1")


def _downloads(v: vm.QbrView):
    stamp = dt.date.today().strftime("%Y%m%d")
    fname = f"qbr_{v.safe_period}_{stamp}"
    btn = ("rounded border border-slate-300 px-3 py-1.5 text-sm font-medium "
           "text-slate-700 hover:bg-slate-50")
    return Div(
        H2("Downloads", cls="mt-6 text-base font-semibold text-slate-900"),
        Div(
            Button(".pptx", type="submit", form="qbr-controls",
                   formaction=f"{BASE}/export/pptx", formmethod="get", cls=btn),
            Button(".md appendix", type="submit", form="qbr-controls",
                   formaction=f"{BASE}/export/md", formmethod="get",
                   cls=btn + " ml-2"),
            P(f"filename: {fname}.pptx / .md", cls="mt-2 text-xs text-slate-400"),
            cls="mt-2",
        ),
    )


def _sub_vertical(v: vm.QbrView):
    if v.sub_vertical is None:
        return P(vm.SUBVERTICAL_UNAVAILABLE, cls="mt-2 text-sm text-slate-500")
    return Div(
        H2("Sub-vertical split", cls="mt-6 text-base font-semibold text-slate-900"),
        Div(data_table(v.sub_vertical["columns"], v.sub_vertical["rows"]), cls="mt-2"),
    )


def _data(v: vm.QbrView):
    return Div(
        Div(metric_cards(v.metrics),
            P(vm.NUMBERS_IDENTICAL, cls="mt-2 text-xs text-slate-500"),
            cls="mt-4"),
        H2("Pipeline by stage", cls="mt-6 text-base font-semibold text-slate-900"),
        Div(_chart(v), cls="mt-2"),
        _sub_vertical(v),
        H2("Top deals", cls="mt-6 text-base font-semibold text-slate-900"),
        Div(data_table(v.top["columns"], v.top["rows"]), cls="mt-2"),
        H2("Risks", cls="mt-6 text-base font-semibold text-slate-900"),
        *[P(n, cls="text-xs text-slate-500") for n in v.risk["notes"]],
        data_table(v.risk["columns"], v.risk["rows"], v.risk["empty_text"]),
        _downloads(v),
        P(vm.FOOTER, cls="mt-8 border-t border-slate-200 pt-3 text-xs text-slate-500"),
        id="qbr-data",
    )


def _full_page(v: vm.QbrView):
    return page(
        "QBR Assembler",
        H1("QBR assembler", cls="text-2xl font-bold text-slate-900"),
        _controls(v), _data(v),
        active=BASE,
    )


def _empty_page():
    return page(
        "QBR Assembler",
        H1("QBR assembler", cls="text-2xl font-bold text-slate-900"),
        P(vm.EMPTY_STATE, cls="mt-4 rounded border border-slate-200 bg-slate-50 "
                              "px-4 py-3 text-slate-600"),
        active=BASE,
    )


def _build(current_id, prior_id, period, team, quota):
    options = vm.snapshot_options()
    cid, pid = _params.resolve(_params.cid(current_id), _params.pid(prior_id), options)
    period = period if period is not None else vm.default_period()
    return vm.build(cid, pid, period or "", team if team is not None else vm.DEFAULT_TEAM,
                    _params.quota(quota))


def _stamp_name(safe_period: str, ext: str) -> str:
    return f"qbr_{safe_period}_{dt.date.today().strftime('%Y%m%d')}.{ext}"


def register(rt):
    @rt(BASE)
    def get(current_id: str = None, prior_id: str = None, period: str = None,
            team: str = None, quota: str = None):
        if not vm.snapshot_options():
            return _empty_page()
        return _full_page(_build(current_id, prior_id, period, team, quota))

    @rt(f"{BASE}/body")
    def get(current_id: str = None, prior_id: str = None, period: str = None,
            team: str = None, quota: str = None):
        return _data(_build(current_id, prior_id, period, team, quota))

    @rt(f"{BASE}/export/pptx")
    def get(current_id: str = None, prior_id: str = None, period: str = None,
            team: str = None, quota: str = None):
        v = _build(current_id, prior_id, period, team, quota)
        meta = {"period": v.period, "team": v.team, "quota": v.quota}
        buf = deck.build_pptx(v.current_id, v.prior_id, meta)
        return Response(
            buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition":
                     f'attachment; filename="{_stamp_name(v.safe_period, "pptx")}"'},
        )

    @rt(f"{BASE}/export/md")
    def get(current_id: str = None, prior_id: str = None, period: str = None,
            team: str = None, quota: str = None):
        v = _build(current_id, prior_id, period, team, quota)
        meta = {"period": v.period, "team": v.team, "quota": v.quota}
        md = deck.build_md(v.current_id, v.prior_id, meta)
        return Response(
            md, media_type="text/markdown",
            headers={"Content-Disposition":
                     f'attachment; filename="{_stamp_name(v.safe_period, "md")}"'},
        )
