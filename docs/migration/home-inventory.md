# Home Inventory — Pipeline Import (tool 0)

Source of truth for the last Streamlit surface ported: `app/Home.py` +
`app/mapping_ui.py` → `web/routes/home.py` + `core/views/home.py`. One row per
`st.*` call plus a sweep of user-facing strings/transforms so nothing escapes
the view model. This tool is a stateful ingest wizard: upload CSV →
mapping-profile select → column-mapping grid (PIPELINE_SCHEMA) → date format →
stage-bucket assignment → validation → confirm import with duplicate-override
and profile save.

**Files inventoried**

- `app/Home.py` — page body (upload/profile, mapping grid, date, stage,
  validation, confirm).
- `app/mapping_ui.py` — `render_mapping_grid`, `render_date_format_choice`,
  `render_stage_assignment`, `render_validation`.
- Core (read-only / write, NOT reimplemented — the route *calls* these):
  `core/importer.py` (`import_snapshot`), `core/mapping.py`
  (`suggest_mapping`, `save_profile`, `load_profiles`), `core/ingest.py`
  (`load_csv`, `apply_mapping`, `infer_date_format`, `parse_date_series`,
  `load_alias_index`), `core/schema.py` (`PIPELINE_SCHEMA`, `validate_frame`),
  `core/store.py` (`save_profile`, `load_profiles`, `list_snapshots`,
  `write_snapshot`, `find_snapshot_by_hash`).

Legend — **VM** = value/string in `core/views/home.py` (or shared
`core/views/common.py`) · **route** = structural HTML/htmx · **DELETE** =
Streamlit rerun/session-state artifact.

---

## A. `st.*` calls — page body (`Home.py`)

| Line | Call | Purpose | Port target |
|------|------|---------|-------------|
| 20 | `st.set_page_config` | page chrome | layout |
| 21–24 | `st.title` / `st.caption` | H1 + caption | route (static) + `vm.CAPTION` |
| 32 | `st.file_uploader` | CSV upload | route `<input type=file>` + upload token |
| 33–35 | `mapping.load_profiles` / `st.selectbox` | mapping-profile select | **VM** `profile_options` + route `<select>` → `/home/reprofile` |
| 37–39 | `st.info(hint)` + `st.stop` | empty state | `vm.UPLOAD_HINT`; **DELETE** stop |
| 42–46 | `ingest.load_csv` / `st.error` / `st.stop` | parse guard | route error render; **DELETE** stop |
| 49–51 | `st.subheader`/`st.caption`/`st.dataframe` | detected columns | route caption ("Detected columns: …") |
| 54–56 | `mapping_ui.render_mapping_grid` + missing-required | per-field select + samples | **VM** `common.import_preview` + route grid |
| 59–62 | `mapping_ui.render_date_format_choice` | date radio + live preview | **VM** `common.import_preview.date` + route radios |
| 65–69 | `mapping_ui.render_stage_assignment` | per-raw-stage bucket select | **VM** `stage_preview` + route selects |
| 72–86 | validation: `apply_mapping` + `validate_frame` + `render_validation` | blocking/warnings | **VM** `validate` + route block |
| 89–97 | `st.columns(3)` + save-as / label / as-of inputs | confirm inputs | route `<input>`s; `vm.default_label` |
| 99–116 | `st.button("Confirm import")` + `save_profile` + `import_snapshot` | commit | route `hx-post /home/import`; **DELETE** disabled-state via `st.session_state` |
| 117–127 | `st.session_state["pending_duplicate"]` + success/warnings | result | route success panel + `vm.import_success` |
| 129–137 | duplicate-override checkbox + `st.rerun` | override flow | route "Import anyway" (`hx-vals override=1`); **DELETE** rerun/session-state |

## B. Shared helpers — `app/mapping_ui.py`

| Helper | Port target |
|--------|-------------|
| `render_mapping_grid` | **VM** `common.import_preview` (schema-parameterized, shared with Account Plan) + route grid |
| `render_date_format_choice` | **VM** `common.import_preview.date` + route radios |
| `render_stage_assignment` | **VM** `home.stage_preview` + route selects |
| `render_validation` | **VM** `home.validate` + route `_validation_block` |

---

## §1a. Workarounds DELETED (not reimplemented)

- **`st.rerun()`** (after import / override tick) — rerun artifacts → htmx region
  swaps (`#home-body` / `#home-grid`).
- **`st.stop()`** ×2 (no-upload, parse error) → render + `return`.
- **`st.session_state`** for `pending_duplicate` / `dup_override` / upload
  persistence → server-side upload token + an "Import anyway" button that re-posts
  with `override=1`.
- **`st.set_page_config`** → base layout owns chrome.

## §1b. Requirements ported VERBATIM (VM symbols)

| String | VM symbol |
|---|---|
| `Read-only, local-only. Nothing is sent anywhere; data stays in data/agents.db.` | `CAPTION` |
| `Upload a pipeline CSV to begin. Sample: sample_data/energy_pipeline_sample.csv` | `UPLOAD_HINT` |
| `Required fields not mapped: ` (+ joined) | `common.REQUIRED_NOT_MAPPED` |
| date-format labels (Auto-detect / US / International / ISO) | `common.DATE_FORMAT_LABELS` |
| `Every date in this file is ambiguous …` | `common.AMBIGUOUS_DATE_ERROR` |
| `Map the stage field to assign stage buckets.` | `STAGE_NEEDS_MAPPING` |
| `Unmapped stage value(s) — assign a bucket: ` (+ joined) | `STAGE_UNMAPPED_PREFIX` |
| `{n} warning(s) — rows import as-is` / `No validation issues.` | route / `NO_VALIDATION_ISSUES` |
| `'New mapping' is a reserved name — profile not saved.` | `RESERVED_NAME_WARNING` |
| `Imported snapshot '{label}': {n} rows, {m} accounts, ${t} total pipeline.` | `import_success()` |
| `Already imported as '{label}' on {imported_at}. …` | `duplicate_warning()` |

---

## §C. Interaction contract → tool 0

| Trigger | htmx behavior |
|---|---|
| **Upload** CSV | `hx-post` (multipart) → stash raw under an upload token → swap `#home-grid` to the reactive form. Honors the currently-selected profile (`hx-include="#profile-select"`). |
| **Profile change** | `hx-post /home/reprofile` (`hx-include="[name='token']"`) → re-prime the grid from the saved profile's mapping / date / stage assignments. |
| **Field / date / stage change** | `hx-post /home/preview`, `hx-include="#home-form"`, `hx-target="#home-grid"`, `hx-trigger="change delay:200ms"`. Recomputes samples + date preview + stage list + validation together. |
| **Confirm import** | `hx-post /home/import` → `save_profile` (unless reserved/blank) + `import_snapshot` → success panel; blocking → re-render with errors. |
| **Duplicate** | import returns the grid + an "Import anyway" button carrying `hx-vals='{"override":"1"}'`. |
| **Every mutating POST** | `hx-sync="this:drop"` + `hx-disabled-elt="this"` + `hx-indicator`. |

- The mapping-grid + date-preview model is **shared** with Account Plan via
  `core/views/common.import_preview(df, mapping, schema, date_format)` — lifted
  out of `core/views/account_plan.py` and parameterized by `schema.Schema`.
- Writes: snapshot rows + mapping profile → the SQLite store (`store.DEFAULT_DB`),
  behind the loopback + CSRF middleware. No config-file writes (profiles live in
  the DB, not YAML). Derived values render through FT components (auto-escaped).

## §D. View-model surface (`core/views/home.py`)

```
CAPTION / UPLOAD_HINT / STAGE_NEEDS_MAPPING / STAGE_UNMAPPED_PREFIX /
NO_VALIDATION_ISSUES / RESERVED_NAME_WARNING / FOOTER / NEW_MAPPING /
STAGE_BUCKETS / (NOT_MAPPED, DATE_FORMAT_LABELS, REQUIRED_NOT_MAPPED via common)

stage_map_defaults() / alias_index() / profile_options(db) / default_label(today)
suggest_pipeline_mapping(headers)
stage_preview(df, mapping, defaults, chosen) -> {rows, unknown, buckets} | None
stage_assignments_from(rows) -> {raw: bucket}   # blanks dropped
validate(df, mapping, date_format, alias) -> {blocking, warnings, error, blocked}
build_grid(df, mapping, date_format, chosen_stages, stage_defaults, alias)
    -> {preview, stage, validation, blocked}
import_success(...) / duplicate_warning(dup)
```

Tests: `tests/test_home_view.py` (green-suite gate) + `tests/test_home_route.py`
(TestClient with loopback base_url + same-origin Origin so POSTs clear the
guard; `store.DEFAULT_DB` isolated to a tmp copy).

## Checkpoint

Home ported; Streamlit fully retired (`app/` deleted, `streamlit` dropped from
requirements). Suite green. `core/` additive-only apart from the shared
`common.import_preview` lift (Account Plan delegates to it; its parity goldens
stay green).
