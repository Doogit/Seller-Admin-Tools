# Task 13 Inventory — Account Plan (tool 3)

Source of truth for the port. One row per `st.*` call in the page body, the
shared helpers it uses, and a **sweep of every user-facing string / transform**
so nothing escapes the view model (`core/views/account_plan.py`) and the parity
gate. This is the busiest of the three pages: an upload → map → validate →
import grid, an account/snapshot selector, an alias-confirm branch, a plan
render, a product-assign branch, and two downloads.

**Files inventoried**

- `app/pages/3_Account_Plan.py` — page body.
- `app/mapping_ui.py` — `render_mapping_grid`, `render_date_format_choice`
  (reused by the import grid; modelled purely in `import_preview`).
- Core (read-only, NOT reimplemented — the view model *calls* these):
  `core/crosswalk.py` (`gap_table`, `whitespace_estimate`, `load_obligation_map`,
  `load_product_map`, `append_product_alias`, `split_list`), `core/plan.py`
  (`compose`, `plan_md`, `plan_pptx`), `core/importer.py`
  (`import_account_facts`), `core/ingest.py` (`load_csv`, `infer_date_format`,
  `parse_date_series`, `append_alias`, `load_alias_index`), `core/mapping.py`
  (`suggest_mapping`), `core/store.py`
  (`load_/upsert_/delete_account_facts`, `list_snapshots`, `get_opportunities`),
  `core/schema.py` (`ACCOUNT_SCHEMA`).

Legend for **Port target**: **VM** = value/string in the view model · **route**
= structural HTML/htmx in `web/routes/account_plan.py` · **layout** = base
skeleton (`web/components.py`) · **DELETE** = Streamlit rerun/exec artifact.

---

## A. `st.*` calls — page body (`3_Account_Plan.py`)

| # | Line | Call | Purpose | Port target |
|---|------|------|---------|-------------|
| 1 | 24 | `st.set_page_config(...)` | page chrome | **layout** |
| 2 | 25 | `st.title("Account plan generator")` | H1 | **route** (static) |
| 3 | 28 | `st.expander("Import account-facts CSV", expanded=facts.empty)` | import panel | **route** `<details>`; open when no facts |
| 4 | 29 | `st.file_uploader(...)` | CSV upload | **route** `<input type=file>` + upload token (§C) |
| 5 | 32–35 | `ingest.load_csv` / `st.error` / `st.stop` | parse guard | **route** error render; **DELETE** `st.stop` |
| 6 | 36 | `st.dataframe(df.head(5))` | raw preview | **route** table (out of parity scope) |
| 7 | 37 | `mapping.suggest_mapping(cols, ACCOUNT_SCHEMA)` | suggestions | **VM** `suggest_facts_mapping` |
| 8 | 38–40 | `mapping_ui.render_mapping_grid(...)` | per-field select + samples | **VM** `import_preview.sections` + **route** grid (§C) |
| 9 | 41–43 | `mapping_ui.render_date_format_choice(...)` | date radio + live preview | **VM** `import_preview.date` + **route** (§C) |
| 10 | 44–46 | `missing = [...]` / `st.error("Required fields not mapped: …")` | required guard | **VM** `import_preview.missing_required` + `REQUIRED_NOT_MAPPED` |
| 11 | 47 | `st.button("Import account facts", type="primary")` | commit import | **route** `hx-post /account-plan/facts/import` (§C) |
| 12 | 48–52 | `importer.import_account_facts(...)` | write facts | **route** calls core (config/db write) |
| 13 | 53–56 | `st.error(b)` per blocking | blocking issues | **route** render `result.blocking` |
| 14 | 57–59 | `st.success(...)` + `st.warning(w)` | import result | **route** render `result.warnings` |
| 15 | 60 | `st.rerun()` | refresh after import | **DELETE** → htmx swap to the selector/plan |
| 16 | 62–66 | `facts.empty` → `st.info(EMPTY_STATE)` + `st.stop` | empty state | **VM** `EMPTY_STATE` + **route** return; **DELETE** stop |
| 17 | 69–84 | `st.columns(2)` + two `st.selectbox` (Account, Pipeline snapshot) | selectors | **VM** `account_options` / `snapshot_options` + **route** `<select>` (§C) |
| 18 | 79 | `st.warning("No pipeline snapshots …")` | no-snapshot note | **VM** `NO_PIPELINE_SNAPSHOTS` |
| 19 | 90–120 | facts↔pipeline join + zero-match `st.warning` + alias `st.selectbox`/`st.button`/`st.caption` | alias-confirm branch | **VM** `build().zero_match` (warning/candidates/no-near text) + **route** confirm POST (§C) |
| 20 | 108–118 | `ingest.append_alias` + `store.upsert/delete_account_facts` + `st.rerun` | persist alias | **route** POST `/account-plan/alias`; **DELETE** rerun |
| 21 | 123–129 | `crosswalk.gap_table` + `st.warning(w)` + `st.info(NO_OBLIGATIONS)` | crosswalk + warnings | **VM** `build().warnings` / `gaps.empty_text` |
| 22 | 131–132 | `whitespace_estimate` + `plan.compose` | analytics | **VM** (shared `_compute`) |
| 23 | 134–136 | `st.subheader` + `st.caption` per summary bit | plan header | **VM** `account_display` / `summary` + **route** |
| 24 | 138–142 | `st.columns(3)` + three `st.metric` | metric cards | **VM** `metrics` + labels `METRIC_*` |
| 25 | 144–149 | `st.subheader` + status-glyph map + `st.dataframe(display)` | gap table | **VM** `gaps` (glyph-prefixed status) + **route** table |
| 26 | 151–155 | uncovered `st.subheader` + `st.write` loop | uncovered gaps | **VM** `uncovered.rows` + **route** list |
| 27 | 157–168 | unresolved products: `st.columns` + `st.selectbox` + `st.button("Assign")` + `st.rerun` | product-assign branch | **VM** `unresolved.{products,categories}` + **route** POST `/account-plan/product`; **DELETE** rerun |
| 28 | 170–172 | `st.subheader` + `st.dataframe(sections["pipeline"])` | open pipeline | **VM** `pipeline` + **route** table |
| 29 | 174–177 | next actions `st.write` loop + relationship `st.caption` | next actions | **VM** `next_actions` / `relationship_map` + **route** |
| 30 | 180–196 | `st.subheader("Downloads")` + two `st.download_button` + two `st.caption` | export | **route** dot-less download routes streaming `plan.plan_pptx/plan_md`; strings in **VM** |

> ~49 `st.*` call sites once the grid/date/stage helpers' internal `st.*` are
> counted. The three `st.rerun()` (import / alias / product) and the two
> `st.stop()` are all **DELETE** (§1a).

## B. Shared helpers — `app/mapping_ui.py`

| Helper | Internal `st.*` | Produces | Port target |
|--------|------------------|----------|-------------|
| `render_mapping_grid` | `st.subheader`, `st.columns`, `st.selectbox`, `st.caption` | per-field source-column pick + 3 sample values | **VM** `import_preview.sections` + **route** grid |
| `render_date_format_choice` | `st.radio`, `st.caption`/`st.error` | date-format choice + live parsed preview / ambiguous+conflict errors | **VM** `import_preview.date` + **route** radio |

---

## §1a. Workarounds to DELETE (not reimplemented)

- **`st.rerun()`** ×3 (L60 import, L118 alias, L168 product) — rerun-persistence
  artifacts. Replaced by htmx swaps of the affected region.
- **`st.stop()`** ×2 (L35 parse error, L66 empty state) → render + `return`.
- **`st.set_page_config`** (L24) → base layout owns page chrome.
- **`st.session_state`** upload persistence — replaced by a server-side upload
  token keyed dict (single-user local); see §C.

## §1b. Requirements that PORT VERBATIM (string-for-string)

| Verbatim string | Source | VM symbol |
|---|---|---|
| `Import an account-facts CSV to begin. Sample: sample_data/account_facts_sample.csv` | L64 empty state | `EMPTY_STATE` |
| `No obligations in scope — set regulatory_scope in the account facts to drive the crosswalk.` | L128 | `NO_OBLIGATIONS` / `gaps.empty_text` |
| `'{raw}' matches zero pipeline rows in this snapshot — likely a name-spelling difference.` | L96 | `zero_match_warning()` |
| `No near-name pipeline accounts found.` | L120 | `NO_NEAR_NAMES` |
| `No pipeline snapshots — plan will render without pipeline.` | L79 | `NO_PIPELINE_SNAPSHOTS` |
| `Required fields not mapped: ` (+ joined) | L46 | `REQUIRED_NOT_MAPPED` |
| metric labels `Whitespace (gap-category pipeline)` / `Uncovered gaps (no play yet)` / `Obligations in scope` | L139–142 | `METRIC_WHITESPACE/UNCOVERED/OBLIGATIONS` |
| status glyphs 🟢 landed / 🟡 partial / 🔴 gap | L146 | `STATUS_EMOJI` |
| `(fill in — relationship map stays human)` | `plan.compose` (core) | `relationship_map` (parity-covered) |
| obligation-map `disclaimer` + `Draft — review before use. Read-only: nothing is sent anywhere.` | L195–196 | `disclaimer` / `FOOTER` |

> `plan.plan_md` / `plan.plan_pptx` strings are core and covered byte-for-byte
> (`.md`) / parsed (`.pptx`) by the Task 13 goldens. The VM never restates them.

---

## §C. Interaction contract → tool 3 (Task 14)

| Trigger | htmx behavior | Rationale |
|---|---|---|
| **Upload** account-facts CSV | `hx-post` (multipart) → server stashes the raw CSV under an **upload token** (module dict, single-user local) → swap the mapping-grid region. | The CSV must survive across per-field preview requests without re-upload. |
| **Field / date-format change** | `hx-trigger="change delay:200ms"`, `hx-include` the whole form, `hx-target` the preview/grid region, `hx-swap` the grid. Re-runs `import_preview` (samples + date preview + missing-required). | Reactive map without a rerun. |
| **Import** button | `hx-post /account-plan/facts/import` → core `import_account_facts` → swap to the selector + plan. | Config/db write; behind the CSRF guard. |
| **Account / snapshot change** | `hx-get` → swap the whole plan region (new `build`). | Plan is keyed to account+snapshot. |
| **Alias-confirm** | `hx-post /account-plan/alias` → `append_alias` + `upsert`/`delete` facts → swap plan. | Config + db write. |
| **Product-assign** | `hx-post /account-plan/product` → `append_product_alias` → swap the unresolved region. | Config write. |
| **Every mutating POST** | `hx-sync="this:drop"` + `hx-disabled-elt="this"` + `hx-indicator`. | Double-submit / in-flight protection. |
| **Downloads** | dot-less routes `/account-plan/export/pptx|md` streaming `plan.plan_pptx/plan_md` via `export_inputs`; filename `account_plan_{safe_name}_{stamp}`. | Dot-less avoids the static-ext route shadow (404). |

- **Config writes** (alias, product-assign, facts import) sit behind the
  loopback + CSRF middleware landed separately. **Do NOT** wrap account /
  opportunity / product / free-text fields in `NotStr` / raw HTML — FT
  components auto-escape; keep it that way.

---

## §D. View-model surface (`core/views/account_plan.py`) — as built

Pure functions, no UI imports; all §B/§1b strings produced here once.

```
EMPTY_STATE / NO_OBLIGATIONS / NO_NEAR_NAMES / NO_PIPELINE_SNAPSHOTS /
REQUIRED_NOT_MAPPED / FOOTER / METRIC_* / STATUS_EMOJI / NOT_MAPPED /
DATE_FORMAT_LABELS / AMBIGUOUS_DATE_ERROR / zero_match_warning()

has_facts(db) -> bool
account_options(db) -> [(account_name, display)]      # display = raw or name
snapshot_options(db) -> [(id, label)]                 # via common
product_assign_categories() -> [str]                  # sorted product_map keys

suggest_facts_mapping(headers) -> mapping
import_preview(df, mapping, date_format) -> {sections, date, missing_required}

export_inputs(account, snapshot_id, db) -> (sections, disclaimer)   # downloads
build(account, snapshot_id, db) -> AccountPlanView:
    account_display, summary, metrics{whitespace,uncovered,obligations},
    gaps{columns,rows,empty_text}, uncovered{rows},
    unresolved{products,categories}, pipeline{columns,rows},
    next_actions, relationship_map, warnings, zero_match|None,
    disclaimer, safe_name
```

Tests: `tests/test_account_plan_view.py` (green-suite gate) +
`tests/test_account_plan_parity.py` (parametrized over `BUILDERS`, `ALLOWLIST`
empty) against goldens frozen by `tests/goldens/account_plan/capture.py`.

## Checkpoint

Task 13 complete: view model + fixtures + goldens (`.plan.md` byte, `.pptx.json`
parsed, `.view.json` struct) + view/parity tests. Suite green (134). Core
additive-only (`core/views/account_plan.py`). Task 14 (route) is next and edits
`web/server.py` — sequence after the separate security layer lands.
