"""Home route — the pipeline-import wizard (upload → column mapping → date
format → stage-bucket assignment → validation → confirm import), ported from
app/Home.py + app/mapping_ui.py. Renders strictly from core.views.home; no
user-facing string is built here except static structural labels.

Interaction (mirrors the Account Plan import grid, plus Home's extras):
  - Upload stashes the CSV once under an opaque token (module dict, single-user
    local); every reactive re-render posts only the token + form, never re-sends
    the file.
  - A single reactive Form (#home-form) holds the mapping selects, date radios,
    stage-bucket selects and confirm inputs. Any select/radio change re-posts to
    /home/preview and swaps the whole grid, so samples, the date preview, the
    stage list and validation all recompute together.
  - The mapping-profile select (outside the form) re-primes the grid from a
    saved profile via /home/reprofile.
  - Confirm import writes a snapshot (importer.import_snapshot) and optionally
    saves the profile (mapping.save_profile); a duplicate file surfaces an
    "Import anyway" override. All writes are POSTs behind the loopback + CSRF
    middleware. Derived values render through FT components (auto-escaped).

Regions (htmx targets):
  #home-body   — everything below H1 (import panel, or the success panel).
  #home-grid   — the reactive mapping/date/stage/validation/confirm form.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fasthtml.common import (
    A, Button, Details, Div, Form, H1, H3, Input, Label, Option, P, Select,
    Span, Summary,
)
from starlette.requests import Request

from core import importer, ingest, mapping, schema
from core.views import home as vm
from web.components import page

BASE = "/home"

# Server-side stash of uploaded pipeline CSVs, keyed by an opaque token so the
# reactive previews never re-upload the file (single-user local tool).
_UPLOADS: dict[str, bytes] = {}

_SEL = ("block w-full rounded border border-border px-2 py-1 text-sm "
        "focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand")
_BTN = ("rounded bg-brand px-3 py-1.5 text-sm font-medium text-white "
        "hover:bg-brand-dark disabled:opacity-50")
_BTN2 = ("rounded border border-border px-3 py-1.5 text-sm font-medium "
         "text-ink hover:bg-bg")
_H2 = "text-base font-semibold text-ink"
_LBL = "block text-xs font-medium text-muted"
# Notice level -> a literal class string (Tailwind can't tree-shake a class name
# built by interpolation, so these must be spelled out).
_NOTICE_CLS = {"red": "mt-1 text-sm text-high-ink",
               "amber": "mt-1 text-sm text-medium-ink"}


# --- form parsing ------------------------------------------------------------

def _mapping_from_form(form) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for field in schema.PIPELINE_SCHEMA.all_fields:
        out[field] = form.get(f"map_{field}") or None
    return out


def _stages_from_form(form) -> dict[str, str]:
    chosen: dict[str, str] = {}
    for k, v in form.multi_items():
        if k.startswith("sb:"):
            chosen[k[3:]] = v
    return chosen


def _profile_defaults(profile_name: str):
    """(stage-bucket defaults = stage_map ∪ profile, profile dict|None)."""
    defaults = dict(vm.stage_map_defaults())
    profile = mapping.load_profiles().get(profile_name)
    if profile:
        defaults.update(profile["stage_assignments"])
    return defaults, profile


# --- reactive grid -----------------------------------------------------------

def _field_rows(section: dict):
    rows = []
    for f in section["fields"]:
        samp = (Span("e.g. " + " | ".join(f["samples"]), cls="text-xs text-muted")
                if f["samples"] else Span("", cls="text-xs text-muted"))
        rows.append(Div(
            Div(Label(f["field"], fr=f"map_{f['field']}",
                      cls="text-sm font-medium text-ink"),
                P(f["description"], cls="text-xs text-muted")),
            Select(*(Option(o, value=("" if o == vm.NOT_MAPPED else o),
                            selected=(o == f["selected"]))
                     for o in f["options"]),
                   id=f"map_{f['field']}", name=f"map_{f['field']}", cls=_SEL,
                   hx_post=f"{BASE}/preview", hx_include="#home-form",
                   hx_target="#home-grid", hx_swap="innerHTML",
                   hx_trigger="change delay:200ms"),
            samp,
            cls="grid gap-2 sm:grid-cols-3 items-start py-1",
        ))
    return rows


def _date_block(date: dict | None, date_format: str):
    if date is None:
        return ""
    radios = [
        Label(Input(type="radio", name="date_format", value=k,
                    checked=(k == date_format),
                    hx_post=f"{BASE}/preview", hx_include="#home-form",
                    hx_target="#home-grid", hx_swap="innerHTML",
                    hx_trigger="change", cls="mr-1"),
              lbl, cls="mr-4 text-sm text-ink")
        for k, lbl in vm.DATE_FORMAT_LABELS.items()
    ]
    if date["error"]:
        prev = P(date["error"], cls="mt-1 text-sm text-high-ink")
    else:
        txt = "Preview ({}): {}".format(
            date["resolved"],
            " | ".join(f"{r['raw']} → {r['parsed']}" for r in date["rows"]))
        prev = P(txt, cls="mt-1 text-xs text-muted")
    return Div(P("Date format", cls="mt-4 text-sm font-medium text-ink"),
               Div(*radios, cls="mt-1"), prev)


def _stage_block(stage: dict | None):
    if stage is None:
        return Div(H3("Stage buckets", cls=f"mt-4 {_H2}"),
                   P(vm.STAGE_NEEDS_MAPPING, cls="mt-1 text-sm text-muted"))
    warn = (P(vm.STAGE_UNMAPPED_PREFIX + ", ".join(stage["unknown"]),
              cls="mt-1 text-sm text-medium-ink") if stage["unknown"] else "")
    cards = []
    for r in stage["rows"]:
        cards.append(Div(
            Label(r["raw"], fr=f"sb:{r['raw']}", cls="text-sm text-ink"),
            Select(*(Option(b or "(unassigned)", value=b, selected=(b == r["bucket"]))
                     for b in stage["buckets"]),
                   id=f"sb:{r['raw']}", name=f"sb:{r['raw']}", cls=_SEL,
                   hx_post=f"{BASE}/preview", hx_include="#home-form",
                   hx_target="#home-grid", hx_swap="innerHTML",
                   hx_trigger="change delay:200ms"),
            cls="py-1"))
    return Div(H3("Stage buckets", cls=f"mt-4 {_H2}"), warn,
               Div(*cards, cls="mt-1 grid gap-2 sm:grid-cols-3"))


def _blocking_line(text):
    # "Blocked" word marks severity textually, so a blocker is distinguishable
    # from a warning without relying on hue alone (both are status-colored).
    return P(Span("Blocked", cls="mr-1.5 font-semibold uppercase tracking-wide"),
             text, cls="mt-1 text-sm text-high-ink")


def _validation_block(v: dict):
    if v["error"]:
        return Div(H3("Validation", cls=f"mt-4 {_H2}"), _blocking_line(v["error"]))
    body = [_blocking_line(b) for b in v["blocking"]]
    if v["warnings"]:
        body.append(Details(
            Summary(f"{len(v['warnings'])} warning(s) — rows import as-is",
                    cls="cursor-pointer text-sm font-medium text-medium-ink"),
            *[P(w, cls="mt-1 text-sm text-medium-ink") for w in v["warnings"]],
            open=True, cls="mt-1"))
    if not v["blocking"] and not v["warnings"]:
        body.append(P(vm.NO_VALIDATION_ISSUES, cls="mt-1 text-sm text-positive-ink"))
    return Div(H3("Validation", cls=f"mt-4 {_H2}"), *body)


def _confirm_block(save_as: str, label: str, as_of: str, blocked: bool,
                   dup: dict | None):
    grid = Div(
        Div(Label("Save profile as", fr="save_as", cls=_LBL),
            Input(id="save_as", name="save_as", value=save_as, cls=_SEL)),
        Div(Label("Snapshot label", fr="label", cls=_LBL),
            Input(id="label", name="label", value=label, cls=_SEL)),
        Div(Label("Data as-of date", fr="as_of", cls=_LBL),
            Input(type="date", id="as_of", name="as_of", value=as_of, cls=_SEL)),
        cls="mt-2 grid gap-3 sm:grid-cols-3")
    confirm = Button("Confirm import", type="button", disabled=(blocked or not label),
                     hx_post=f"{BASE}/import", hx_include="#home-form",
                     hx_target="#home-body", hx_swap="outerHTML",
                     hx_sync="this:drop", hx_disabled_elt="this",
                     hx_indicator="#home-spin", cls=f"mt-3 {_BTN}")
    actions = [confirm]
    if dup:
        actions = [
            P(vm.duplicate_warning(dup), cls="mt-3 text-sm text-medium-ink"),
            Button("Import anyway", type="button",
                   hx_post=f"{BASE}/import", hx_include="#home-form",
                   hx_vals='{"override": "1"}',
                   hx_target="#home-body", hx_swap="outerHTML",
                   hx_sync="this:drop", hx_disabled_elt="this",
                   hx_indicator="#home-spin", cls=f"mt-2 {_BTN}"),
        ]
    return Div(
        H3("Confirm import", cls=f"mt-6 {_H2}"), grid,
        Div(*actions,
            Span("importing…", id="home-spin",
                 cls="htmx-indicator ml-2 text-xs text-muted"),
            cls="flex flex-wrap items-center"),
        P(vm.FOOTER, cls="mt-2 text-xs text-muted"),
    )


def _grid_form(token: str, field_mapping, date_format: str, chosen_stages: dict,
               profile_name: str, save_as: str, label: str, as_of: str,
               dup: dict | None = None, notices=()):
    raw = _UPLOADS[token]
    df = ingest.load_csv(raw)
    defaults, _ = _profile_defaults(profile_name)
    grid = vm.build_grid(df, field_mapping, date_format, chosen_stages,
                         defaults, vm.alias_index())
    sections = [Div(H3(s["title"], cls="mt-3 text-sm font-semibold text-ink"),
                    *_field_rows(s))
                for s in grid["preview"]["sections"]]
    missing = grid["preview"]["missing_required"]
    guard = (P(vm.REQUIRED_NOT_MAPPED + ", ".join(missing),
               cls="mt-2 text-sm text-high-ink") if missing else "")
    return Form(
        Input(type="hidden", name="token", value=token),
        Input(type="hidden", name="profile", value=profile_name),
        P("Detected columns: " + ", ".join(df.columns),
          cls="text-xs text-muted"),
        *[P(t, cls=_NOTICE_CLS[c]) for t, c in notices],
        *sections, guard,
        _date_block(grid["preview"]["date"], date_format),
        _stage_block(grid["stage"]),
        _validation_block(grid["validation"]),
        _confirm_block(save_as, label, as_of, grid["blocked"], dup),
        id="home-form",
    )


# --- upload panel + body -----------------------------------------------------

def _upload_controls(profile_name: str, grid_inner):
    controls = Div(
        Div(Label("Mapping profile", fr="profile-select", cls=_LBL),
            Select(*(Option(p, value=p, selected=(p == profile_name))
                     for p in vm.profile_options()),
                   id="profile-select", name="profile", cls=_SEL,
                   hx_post=f"{BASE}/reprofile", hx_include="[name='token']",
                   hx_target="#home-grid", hx_swap="innerHTML",
                   hx_trigger="change")),
        Div(Label("Pipeline CSV export", fr="pipeline_csv", cls=_LBL),
            Input(type="file", id="pipeline_csv", name="pipeline_csv", accept=".csv",
                  cls="mt-1 block text-sm",
                  hx_post=f"{BASE}/upload", hx_target="#home-grid",
                  hx_swap="innerHTML", hx_encoding="multipart/form-data",
                  hx_include="#profile-select", hx_trigger="change")),
        cls="grid gap-3 sm:grid-cols-2")
    return Div(controls, Div(grid_inner, id="home-grid", cls="mt-4"))


def _import_panel(expanded: bool, profile_name: str = vm.NEW_MAPPING, grid_inner=None):
    return Details(
        Summary("Import pipeline CSV",
                cls="cursor-pointer text-sm font-medium text-ink"),
        Div(_upload_controls(profile_name,
                             grid_inner if grid_inner is not None
                             else P(vm.UPLOAD_HINT, cls="text-muted")),
            cls="mt-3"),
        open=expanded,
        cls="rounded border border-border bg-surface px-4 py-3",
    )


def _body():
    return Div(_import_panel(True), id="home-body")


def _success_body(message: str, warnings: list[str]):
    return Div(
        P(message, cls="rounded-md border-l-4 border-positive bg-positive-tint "
                       "px-4 py-3 text-positive-ink"),
        *[P(w, cls="mt-2 text-sm text-medium-ink") for w in warnings],
        A("Import another CSV", href=BASE, cls=f"mt-4 inline-block {_BTN2}"),
        id="home-body")


def _full_page():
    return page("Pipeline Import",
                H1("Pipeline import & column mapping",
                   cls="text-2xl font-bold text-ink"),
                P(vm.CAPTION, cls="mt-1 text-muted"),
                _body(), active=BASE)


def _prefill(profile):
    """(mapping, date_format, save_as) from a profile or the raw suggestions."""
    return profile["mapping"], profile.get("date_format", "auto")


# --- registration ------------------------------------------------------------

def register(rt):
    @rt(BASE)
    def get():
        return _full_page()

    @rt(f"{BASE}/upload", methods=["post"])
    async def post(request: Request):
        form = await request.form()
        upload = form.get("pipeline_csv")
        if upload is None or not hasattr(upload, "read"):
            return P("No file received.", cls="text-sm text-high-ink")
        raw = await upload.read()
        try:
            df = ingest.load_csv(raw)
        except ingest.IngestError as e:
            return P(str(e), cls="text-sm text-high-ink")
        token = uuid.uuid4().hex
        _UPLOADS[token] = raw
        return _rendered_grid(token, df, form.get("profile", vm.NEW_MAPPING))

    @rt(f"{BASE}/reprofile", methods=["post"])
    async def post(request: Request):
        form = await request.form()
        raw = _UPLOADS.get(form.get("token", ""))
        if raw is None:
            return P(vm.UPLOAD_HINT, cls="text-muted")
        df = ingest.load_csv(raw)
        return _rendered_grid(form["token"], df, form.get("profile", vm.NEW_MAPPING))

    @rt(f"{BASE}/preview", methods=["post"])
    async def post(request: Request):
        form = await request.form()
        raw = _UPLOADS.get(form.get("token", ""))
        if raw is None:
            return P("Upload expired — re-select the CSV.", cls="text-sm text-high-ink")
        today = dt.date.today().isoformat()
        return _grid_form(
            form["token"], _mapping_from_form(form),
            form.get("date_format", "auto"), _stages_from_form(form),
            form.get("profile", vm.NEW_MAPPING), form.get("save_as", ""),
            form.get("label", ""), form.get("as_of") or today)

    @rt(f"{BASE}/import", methods=["post"])
    async def post(request: Request):
        form = await request.form()
        raw = _UPLOADS.get(form.get("token", ""))
        if raw is None:
            return _body()
        token = form["token"]
        field_mapping = _mapping_from_form(form)
        date_format = form.get("date_format", "auto")
        chosen = _stages_from_form(form)
        profile_name = form.get("profile", vm.NEW_MAPPING)
        save_as = form.get("save_as", "").strip()
        label = form.get("label", "").strip()
        override = form.get("override") == "1"
        try:
            as_of = dt.date.fromisoformat(form.get("as_of", ""))
        except ValueError:
            as_of = dt.date.today()

        def rerender(dup=None, notices=()):
            return Div(_import_panel(
                True, profile_name,
                _grid_form(token, field_mapping, date_format, chosen, profile_name,
                           save_as, label, as_of.isoformat(), dup=dup,
                           notices=notices)),
                id="home-body")

        # Re-validate server-side (the button's disabled state can be stale).
        grid = vm.build_grid(ingest.load_csv(raw), field_mapping, date_format,
                             chosen, *_defaults_and_alias(profile_name))
        if grid["blocked"] or not label:
            note = [] if label else [("Enter a snapshot label to import.", "red")]
            return rerender(notices=note)

        stage_assignments = vm.stage_assignments_from(grid["stage"]["rows"])
        reserved = save_as.lower() == vm.NEW_MAPPING.lower()
        app_warnings = [vm.RESERVED_NAME_WARNING] if reserved else []
        profile_id = None
        if save_as and not reserved:
            profile_id = _save_profile(save_as, field_mapping, stage_assignments,
                                       date_format)

        result = importer.import_snapshot(
            raw, field_mapping, date_format, stage_assignments, label,
            as_of_date=as_of, on_duplicate="override" if override else "ask",
            profile_id=profile_id, alias_index=vm.alias_index())
        notices = [(w, "amber") for w in app_warnings]
        if result.skipped:
            return rerender(dup=result.duplicate_of, notices=notices)
        if result.blocking:
            return rerender(notices=notices + [(b, "red") for b in result.blocking])
        _UPLOADS.pop(token, None)
        return _success_body(
            vm.import_success(label, result.n_rows, result.n_accounts,
                              result.total_amount),
            app_warnings + result.warnings)


# --- small helpers shared by the handlers ------------------------------------

def _rendered_grid(token: str, df, profile_name: str):
    """Fresh grid from a saved profile (if selected & valid) or suggestions."""
    _, profile = _profile_defaults(profile_name)
    if profile:
        field_mapping, date_format = _prefill(profile)
        save_as = profile_name
    else:
        field_mapping = vm.suggest_pipeline_mapping(list(df.columns))
        date_format, save_as = "auto", ""
    today = dt.date.today()
    return _grid_form(token, field_mapping, date_format, {}, profile_name,
                      save_as, vm.default_label(today), today.isoformat())


def _defaults_and_alias(profile_name: str):
    defaults, _ = _profile_defaults(profile_name)
    return defaults, vm.alias_index()


def _save_profile(name, field_mapping, stage_assignments, date_format) -> int:
    """Save/merge a mapping profile, keeping stage assignments for stages absent
    from this file (Home.py's merge semantics)."""
    existing = mapping.load_profiles().get(name)
    merged = stage_assignments
    if existing:
        merged = {**existing["stage_assignments"], **stage_assignments}
    return mapping.save_profile(name, field_mapping, merged, date_format)
