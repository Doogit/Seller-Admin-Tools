"""Tool 3 route — Account Plan. Renders strictly from the view model
(core/views/account_plan.py); no user-facing string is built here except static
structural labels. Interaction contract: docs/migration/account_plan-inventory.md §C.

The reactive import grid uploads the CSV once to a server-side stash keyed by an
opaque token (module dict — single-user local tool); subsequent per-field /
date-format previews post only the token + mapping, so the file is never
re-sent. All config/db writes (facts import, alias-confirm, product-assign) are
POSTs behind the loopback + CSRF middleware. Derived account / opportunity /
product / free-text values are rendered through FT components (auto-escaped) —
never NotStr / raw HTML.

Regions (htmx targets):
  #ap-body       — everything below H1 (import panel + selector + plan).
  #facts-grid    — the mapping grid (per-field select + samples + date preview).
  #plan          — the rendered plan for the current account + snapshot.
  #unresolved    — the unresolved-product assign block (swapped on assign).
"""

from __future__ import annotations

import datetime as dt
import uuid
from urllib.parse import urlencode

from fasthtml.common import (
    A, Button, Details, Div, Form, H1, H2, H3, Input, Label, Li, Option, P,
    Select, Span, Summary, Ul,
)
from starlette.requests import Request
from starlette.responses import Response

from core import crosswalk, ingest, importer, plan, schema, store
from core.views import account_plan as vm
from web.components import data_table, page
from web.routes import _params

BASE = "/account-plan"
ALIASES_PATH = crosswalk.REPO_ROOT / "config" / "aliases.yaml"

# Server-side stash of uploaded account-facts CSVs, keyed by an opaque token so
# per-field previews never re-upload the file (single-user local tool).
_UPLOADS: dict[str, bytes] = {}

_SEL = "block w-full rounded border border-slate-300 px-2 py-1 text-sm"
_BTN = ("rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white "
        "hover:bg-slate-700 disabled:opacity-50")
_BTN2 = ("rounded border border-slate-300 px-3 py-1.5 text-sm font-medium "
         "text-slate-700 hover:bg-slate-50")
_H2 = "text-base font-semibold text-slate-900"


# --- import grid -------------------------------------------------------------

def _upload_form():
    return Form(
        Label("Account facts CSV", fr="facts_csv",
              cls="block text-xs font-medium text-slate-600"),
        Input(type="file", id="facts_csv", name="facts_csv", accept=".csv",
              cls="mt-1 block text-sm",
              hx_post=f"{BASE}/facts/upload", hx_target="#facts-grid",
              hx_swap="innerHTML", hx_encoding="multipart/form-data",
              hx_trigger="change"),
        Div(id="facts-grid", cls="mt-4"),
    )


def _facts_grid(token: str, preview: dict, date_format: str):
    sections = []
    for sec in preview["sections"]:
        rows = []
        for f in sec["fields"]:
            samp = (Span("e.g. " + " | ".join(f["samples"]),
                         cls="text-xs text-slate-500")
                    if f["samples"] else Span("", cls="text-xs text-slate-400"))
            rows.append(Div(
                Div(Label(f["field"], fr=f"map_{f['field']}",
                          cls="text-sm font-medium text-slate-700"),
                    P(f["description"], cls="text-xs text-slate-500")),
                Select(*(Option(o, value=("" if o == vm.NOT_MAPPED else o),
                                selected=(o == f["selected"]))
                         for o in f["options"]),
                       id=f"map_{f['field']}", name=f"map_{f['field']}", cls=_SEL,
                       hx_post=f"{BASE}/facts/preview", hx_include="#facts-form",
                       hx_target="#facts-grid", hx_swap="innerHTML",
                       hx_trigger="change delay:200ms"),
                samp,
                cls="grid gap-2 sm:grid-cols-3 items-start py-1",
            ))
        sections.append(Div(H3(sec["title"], cls="mt-3 text-sm font-semibold "
                                                 "text-slate-800"), *rows))

    date = _date_block(preview["date"], date_format)
    missing = preview["missing_required"]
    guard = (P(vm.REQUIRED_NOT_MAPPED + ", ".join(missing),
               cls="mt-2 text-sm text-red-700") if missing else "")
    import_btn = Button("Import account facts", type="button", disabled=bool(missing),
                        hx_post=f"{BASE}/facts/import", hx_include="#facts-form",
                        hx_target="#ap-body", hx_swap="outerHTML",
                        hx_sync="this:drop", hx_disabled_elt="this",
                        hx_indicator="#facts-spin", cls=f"mt-3 {_BTN}")
    return Form(
        Input(type="hidden", name="token", value=token),
        *sections, date, guard,
        Div(import_btn, Span("importing…", id="facts-spin",
                             cls="htmx-indicator ml-2 text-xs text-slate-500"),
            cls="flex items-center"),
        id="facts-form",
    )


def _date_block(date: dict | None, date_format: str):
    if date is None:
        return ""
    radios = [
        Label(Input(type="radio", name="date_format", value=k,
                    checked=(k == date_format),
                    hx_post=f"{BASE}/facts/preview", hx_include="#facts-form",
                    hx_target="#facts-grid", hx_swap="innerHTML",
                    hx_trigger="change", cls="mr-1"),
              lbl, cls="mr-4 text-sm text-slate-700")
        for k, lbl in vm.DATE_FORMAT_LABELS.items()
    ]
    if date["error"]:
        prev = P(date["error"], cls="mt-1 text-sm text-red-700")
    else:
        txt = "Preview ({}): {}".format(
            date["resolved"],
            " | ".join(f"{r['raw']} → {r['parsed']}" for r in date["rows"]))
        prev = P(txt, cls="mt-1 text-xs text-slate-500")
    return Div(P("Date format", cls="mt-3 text-sm font-medium text-slate-700"),
               Div(*radios, cls="mt-1"), prev)


def _mapping_from_form(form) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for field in schema.ACCOUNT_SCHEMA.all_fields:
        val = form.get(f"map_{field}")
        out[field] = val or None
    return out


# --- plan render -------------------------------------------------------------

def _metric(label: str, value):
    return Div(P(label, cls="text-xs font-medium text-slate-500"),
               P(str(value), cls="mt-1 text-xl font-semibold text-slate-900"),
               cls="rounded-lg border border-slate-200 bg-white p-4")


def _alias_block(v: vm.AccountPlanView, account_name: str, snapshot_id):
    z = v.zero_match
    if not z:
        return ""
    body = [P(z["warning"], cls="text-sm text-amber-800")]
    if z["candidates"]:
        body.append(Form(
            Input(type="hidden", name="account_name", value=account_name),
            Input(type="hidden", name="snapshot_id",
                  value=("" if snapshot_id is None else str(snapshot_id))),
            Label("Did you mean this pipeline account?", fr="alias_pick",
                  cls="block text-xs font-medium text-slate-600"),
            Select(*(Option(c, value=c) for c in z["candidates"]),
                   id="alias_pick", name="pick", cls=_SEL),
            Button("Confirm same account", type="button", cls=f"mt-2 {_BTN2}",
                   hx_post=f"{BASE}/alias", hx_include="closest form",
                   hx_target="#plan", hx_swap="outerHTML",
                   hx_sync="this:drop", hx_disabled_elt="this"),
            cls="mt-2",
        ))
    else:
        body.append(P(z["no_candidates_text"], cls="text-xs text-slate-500"))
    return Div(*body, cls="mt-3 rounded border border-amber-300 bg-amber-50 px-3 py-2")


def _unresolved_block(v: vm.AccountPlanView, account_name: str, snapshot_id):
    u = v.unresolved
    if not u["products"]:
        return Div(id="unresolved")
    rows = []
    for product in u["products"]:
        rows.append(Form(
            Input(type="hidden", name="account_name", value=account_name),
            Input(type="hidden", name="snapshot_id",
                  value=("" if snapshot_id is None else str(snapshot_id))),
            Input(type="hidden", name="product", value=product),
            Div(Span(product, cls="text-sm text-slate-800"),
                Select(*(Option(c, value=c) for c in u["categories"]),
                       name="category", cls=_SEL),
                Button("Assign", type="button", cls=_BTN2,
                       hx_post=f"{BASE}/product", hx_include="closest form",
                       hx_target="#unresolved", hx_swap="outerHTML",
                       hx_sync="this:drop", hx_disabled_elt="this"),
                cls="grid gap-2 sm:grid-cols-3 items-center py-1"),
        ))
    return Div(H2("Unresolved products (excluded from whitespace)", cls=f"mt-6 {_H2}"),
               *rows, id="unresolved")


def _plan(v: vm.AccountPlanView, account_name: str, snapshot_id):
    warnings = [P(w, cls="mt-1 text-sm text-amber-800") for w in v.warnings]
    uncovered = ""
    if v.uncovered["rows"]:
        uncovered = Div(
            H2("Uncovered gaps — no play exists yet", cls=f"mt-6 {_H2}"),
            Ul(*(Li(P(f"{r['obligation_id']}: {r['capability_category']} "
                      f"({r['product_label']})", cls="text-sm text-slate-700"))
                 for r in v.uncovered["rows"]), cls="mt-1 list-disc pl-5"))
    pipeline = ""
    if v.pipeline["rows"]:
        pipeline = Div(H2("Open pipeline for account", cls=f"mt-6 {_H2}"),
                       data_table(v.pipeline["columns"], v.pipeline["rows"]))
    qs = urlencode({"account_name": account_name,
                    "snapshot_id": "" if snapshot_id is None else snapshot_id})
    return Div(
        H2(f"Plan — {v.account_display}", cls=_H2),
        *[P(b, cls="text-sm text-slate-600") for b in v.summary],
        _alias_block(v, account_name, snapshot_id),
        Div(_metric(vm.METRIC_WHITESPACE, v.metrics["whitespace"]),
            _metric(vm.METRIC_UNCOVERED, v.metrics["uncovered"]),
            _metric(vm.METRIC_OBLIGATIONS, v.metrics["obligations"]),
            cls="mt-4 grid gap-3 sm:grid-cols-3"),
        *warnings,
        Div(H2("Obligation → capability → gap", cls=f"mt-6 {_H2}"),
            data_table(v.gaps["columns"], v.gaps["rows"], v.gaps["empty_text"])),
        uncovered,
        _unresolved_block(v, account_name, snapshot_id),
        pipeline,
        Div(H2("Next actions", cls=f"mt-6 {_H2}"),
            Ul(*(Li(P(a, cls="text-sm text-slate-700")) for a in v.next_actions),
               cls="mt-1 list-disc pl-5"),
            P(v.relationship_map, cls="mt-2 text-xs text-slate-500")),
        Div(H2("Downloads", cls=f"mt-6 {_H2}"),
            A("Download .pptx", href=f"{BASE}/export/pptx?{qs}", cls=_BTN2),
            A("Download .md", href=f"{BASE}/export/md?{qs}", cls=f"ml-2 {_BTN2}"),
            P(v.disclaimer, cls="mt-2 text-xs text-slate-500"),
            P(vm.FOOTER, cls="text-xs text-slate-500")),
        id="plan",
    )


# --- selector + body ---------------------------------------------------------

def _selector(account_name: str | None, snapshot_id, snap_options):
    accounts = vm.account_options()
    acct = Div(
        Label("Account", fr="account_name",
              cls="block text-xs font-medium text-slate-600"),
        Select(*(Option(disp, value=name, selected=(name == account_name))
                 for name, disp in accounts),
               id="account_name", name="account_name", cls=_SEL,
               hx_get=f"{BASE}/plan", hx_target="#plan", hx_swap="outerHTML",
               hx_include="#ap-selector"),
    )
    if snap_options:
        snap = Div(
            Label("Pipeline snapshot", fr="snapshot_id",
                  cls="block text-xs font-medium text-slate-600"),
            Select(*(Option(lbl, value=str(sid), selected=(sid == snapshot_id))
                     for sid, lbl in snap_options),
                   id="snapshot_id", name="snapshot_id", cls=_SEL,
                   hx_get=f"{BASE}/plan", hx_target="#plan", hx_swap="outerHTML",
                   hx_include="#ap-selector"),
        )
    else:
        snap = Div(P(vm.NO_PIPELINE_SNAPSHOTS, cls="text-sm text-amber-800"),
                   Input(type="hidden", name="snapshot_id", value=""))
    return Form(Div(acct, snap, cls="grid gap-3 sm:grid-cols-2"), id="ap-selector")


def _import_panel(expanded: bool):
    return Details(
        Summary("Import account-facts CSV",
                cls="cursor-pointer text-sm font-medium text-slate-700"),
        Div(_upload_form(), cls="mt-3"),
        open=expanded,
        cls="rounded border border-slate-200 bg-slate-50 px-4 py-3",
    )


def _body():
    if not vm.has_facts():
        return Div(
            _import_panel(True),
            P(vm.EMPTY_STATE, cls="mt-4 rounded border border-slate-200 "
                                  "bg-slate-50 px-4 py-3 text-slate-600"),
            id="ap-body")
    accounts = vm.account_options()
    snap_options = vm.snapshot_options()
    account_name = accounts[0][0]
    snapshot_id = snap_options[0][0] if snap_options else None
    return Div(
        _import_panel(False),
        Div(_selector(account_name, snapshot_id, snap_options), cls="mt-4"),
        Div(_plan(vm.build(account_name, snapshot_id), account_name, snapshot_id),
            cls="mt-6"),
        id="ap-body")


def _full_page():
    return page("Account Plan",
                H1("Account plan generator", cls="text-2xl font-bold text-slate-900"),
                _body(), active=BASE)


def _snapshot_from_form(value: str | None):
    return _params.cid(value)  # reuse int-or-None coercion


# --- registration ------------------------------------------------------------

def register(rt):
    @rt(BASE)
    def get():
        return _full_page()

    @rt(f"{BASE}/facts/upload", methods=["post"])
    async def post(request: Request):
        form = await request.form()
        upload = form.get("facts_csv")
        if upload is None or not hasattr(upload, "read"):
            return P("No file received.", cls="text-sm text-red-700")
        raw = await upload.read()
        try:
            df = ingest.load_csv(raw)
        except ingest.IngestError as e:
            return P(str(e), cls="text-sm text-red-700")
        token = uuid.uuid4().hex
        _UPLOADS[token] = raw
        mapping = vm.suggest_facts_mapping(list(df.columns))
        return _facts_grid(token, vm.import_preview(df, mapping, "auto"), "auto")

    @rt(f"{BASE}/facts/preview", methods=["post"])
    async def post(request: Request):
        form = await request.form()
        raw = _UPLOADS.get(form.get("token", ""))
        if raw is None:
            return P("Upload expired — re-select the CSV.", cls="text-sm text-red-700")
        df = ingest.load_csv(raw)
        mapping = _mapping_from_form(form)
        date_format = form.get("date_format", "auto")
        return _facts_grid(form["token"], vm.import_preview(df, mapping, date_format),
                           date_format)

    @rt(f"{BASE}/facts/import", methods=["post"])
    async def post(request: Request):
        form = await request.form()
        raw = _UPLOADS.get(form.get("token", ""))
        if raw is None:
            return _body()
        mapping = _mapping_from_form(form)
        date_format = form.get("date_format", "auto")
        alias_index = ingest.load_alias_index(ALIASES_PATH)
        result = importer.import_account_facts(raw, mapping, date_format,
                                               alias_index=alias_index)
        if result.blocking:
            df = ingest.load_csv(raw)
            grid = _facts_grid(form["token"], vm.import_preview(df, mapping, date_format),
                               date_format)
            errs = Div(*[P(b, cls="text-sm text-red-700") for b in result.blocking])
            return Div(_import_panel(True), Div(errs, grid, cls="mt-2"), id="ap-body")
        _UPLOADS.pop(form["token"], None)
        return _body()

    @rt(f"{BASE}/plan")
    def get(account_name: str = "", snapshot_id: str = ""):
        return _plan(vm.build(account_name, _snapshot_from_form(snapshot_id)),
                     account_name, _snapshot_from_form(snapshot_id))

    @rt(f"{BASE}/alias", methods=["post"])
    def post(account_name: str = "", pick: str = "", snapshot_id: str = ""):
        ingest.append_alias(pick, account_name, ALIASES_PATH)
        renamed = store.load_account_facts()
        renamed = renamed[renamed["account_name"] == account_name].copy()
        renamed["account_name"] = pick
        store.upsert_account_facts(renamed)
        store.delete_account_facts(account_name)
        sid = _snapshot_from_form(snapshot_id)
        return _plan(vm.build(pick, sid), pick, sid)

    @rt(f"{BASE}/product", methods=["post"])
    def post(account_name: str = "", product: str = "", category: str = "",
             snapshot_id: str = ""):
        crosswalk.append_product_alias(product, category)
        sid = _snapshot_from_form(snapshot_id)
        return _unresolved_block(vm.build(account_name, sid), account_name, sid)

    @rt(f"{BASE}/export/pptx")
    def get(account_name: str = "", snapshot_id: str = ""):
        sections, disclaimer = vm.export_inputs(account_name, _snapshot_from_form(snapshot_id))
        buf = plan.plan_pptx(sections, disclaimer)
        fname = f"account_plan_{vm.safe_name(sections['account_display'])}_{_stamp()}.pptx"
        return Response(
            buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'})

    @rt(f"{BASE}/export/md")
    def get(account_name: str = "", snapshot_id: str = ""):
        sections, disclaimer = vm.export_inputs(account_name, _snapshot_from_form(snapshot_id))
        md = plan.plan_md(sections, disclaimer)
        fname = f"account_plan_{vm.safe_name(sections['account_display'])}_{_stamp()}.md"
        return Response(md, media_type="text/markdown",
                        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


def _stamp() -> str:
    return dt.date.today().strftime("%Y%m%d")
