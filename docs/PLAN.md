# Execution plan — sales-admin-agents (4 PRDs)

Source PRDs: `docs/00-foundation-ingest-mapping.md` → `docs/03-account-plan-generator.md`.
Goal: implement all four sessions to first-version quality, locally, with git history per session. No push to GitHub until all four tools exist (user instruction).

## Environment facts (verified)
- Python 3.14.3, pip 26.0.1, git 2.53. streamlit 1.57.0, pandas 3.0.3, PyYAML 6.0.3 installed. python-pptx NOT installed (install at session 3 per PRD).
- `C:\Users\JustD\Documents\GitHub\seller-admin-tools` contains only `docs/`. Not a git repo yet.

## Key decisions / deviations from PRD letter
1. **Repo root = `seller-admin-tools/`** (the existing directory that already holds the PRDs), not a nested `sales-admin-agents/`. The PRD layout is created directly at repo root. Rationale: user pointed at this directory and said "use git" here; nesting would bury the app one level down.
2. **Git flow**: `git init` on `main` (initial commit = docs + .gitignore + README stub). Each session on its PRD-mandated branch (`feat/foundation-ingest`, `feat/forecast-narrative`, `feat/qbr-assembler`, `feat/account-plan`), merged to local `main` (no-ff) when its verification checklist passes. **No remote, no push, no PR links** — PRD "PR link" outputs are replaced by merge commits until the user says push.
3. **Streamlit verification**: interactive checklist items (upload → map → confirm in a browser) are approximated headlessly:
   - Core logic lives in `core/` pure functions covered by pytest (PRD already mandates this).
   - Pages verified with `streamlit.testing.v1.AppTest` where feasible + an import/render smoke run.
   - Snapshots seeded programmatically through the same `core` functions Home.py calls (a small `sample_data/seed_snapshots.py`; session 3's `make_prior_snapshot.py` builds on it). Deviation is documented; final human-in-browser pass is left to the user at demo time.
4. **Pandas 3.0 / Python 3.14**: use non-deprecated APIs only (no silent `to_datetime` coercion anyway per PRD; explicit dtypes; `pd.NA` handling). If a dependency breaks under 3.14, document and pin the working version in requirements.txt.
5. **requirements.txt pins the versions verified here** (streamlit 1.57.0, pandas 3.0.3, PyYAML 6.0.3, python-pptx at whatever installs cleanly, pytest).
6. **No LLM polish, no manager roll-up page, no branded template** — explicitly backlog per PRD 03.

## Sequencing (strictly serial by dependency; parallelism inside sessions only)
Sessions are hard-chained: 00 → 01 (imports store/schema) → 02 (reuses forecast.py) → 03 (reuses mapping refactor + deck/ui patterns). No cross-session parallelization is safe; efficiency comes from within-session batching (write all core modules, then all tests, run pytest once per iteration loop) and from not re-litigating settled PRD decisions.

### Session 1 — Foundation (branch `feat/foundation-ingest`)
1. Scaffold repo layout per PRD (README with "Data handling" section, .gitignore: `data/`, root `*.csv` with `!sample_data/**`, `__pycache__`, `.venv`).
2. `core/schema.py` (REQUIRED/OPTIONAL field dicts + `validate_frame`), `core/ingest.py` (`load_csv` with BOM/semicolon/parenthesized-negative handling, explicit `date_format` incl. `auto` ambiguity rule; `normalize_name` + aliases), `core/mapping.py` (`suggest_mapping` synonym fuzzy match, profile save/load), `core/store.py` (SQLite `data/agents.db`; mapping_profiles, snapshots w/ file_sha256 dup guard, opportunities append-only, index).
3. `config/stage_map.yaml` (generic + MCEM example labels), `config/aliases.yaml` (Meridian pre-seeded).
4. `app/Home.py` single-page flow per PRD steps 1–7.
5. `sample_data/energy_pipeline_sample.csv` — 40 rows with every mandated failure class (2 unmapped stages, 1 malformed date, 03/04/2026 ambiguous pair, 1 negative amount, Meridian variants, messy headers, Opportunity ID).
6. Tests `test_mapping.py`, `test_ingest.py` per PRD list. Verify: pytest green; seed a snapshot; SQLite counts (40 rows, Meridian counted once); grep guard for msx/mssales.
   - Verify: `pytest` → pass; `sqlite3` counts via Python (no sqlite3 CLI assumed on Windows).

### Session 2 — Forecast narrative (branch `feat/forecast-narrative`)
1. `core/forecast.py`: `bucket_rollup` (forecast_category precedence, stage-derived fallback + label), `wow_delta` (opportunity_id precedence, normalized-name fallback, unmatched bucket, None prior handling), `risk_flags` driven by `config/risk_rules.yaml` (stalled = consecutive-snapshot stage age with insufficient-history reporting; slipped; no_sponsor; big_and_late) with evidence strings.
2. `core/narrative.py` + `config/narrative_templates.yaml` — deterministic 3-section draft, numbers verbatim from rollup.
3. `app/pages/1_Forecast_Narrative.py` per PRD (snapshot selectors, metric cards, editable text areas, risk table, `st.code` export + .md download, draft footer).
4. `tests/test_forecast.py` per PRD list (incl. renamed-opp identity via opportunity_id, second synthetic in-test snapshot for slipped, stalled boundary cases).
5. Seed a second snapshot (mutated copy of sample) so WoW demos work.
   - Verify: pytest; traceability spot-check (narrative $ == SQL sum); required-only profile degrades gracefully; offline by construction (no network calls anywhere).

### Session 3 — QBR assembler (branch `feat/qbr-assembler`)
1. `pip install python-pptx`, pin in requirements.txt.
2. Extend `core/forecast.py`: `stage_distribution`, `top_deals`, `owner_rollup` (alias-normalized owner test), `sub_vertical_split` (graceful skip). Tests added.
3. `core/deck.py` (`build_pptx` 5 slides per PRD — native bar chart, capped/truncated top-deals table, DRAFT footer; `build_md`), `core/styles.py` constants.
4. `app/ui.py` shared render helpers extracted from page 1; `app/pages/2_QBR_Assembler.py`.
5. `sample_data/make_prior_snapshot.py` (documented mutation script) if second snapshot not already present.
6. `tests/test_deck.py` consistency guard: parse commit figure back out of built pptx, numeric-compare to `bucket_rollup`.
   - Verify: pytest incl. guard; pptx opens via python-pptx re-read (5 slides, chart, footer); `git check-ignore data/agents.db`.

### Session 4 — Account plan (branch `feat/account-plan`)
1. **Refactor first, commit separately**: `schema.py` → `PIPELINE_SCHEMA` / `ACCOUNT_SCHEMA` objects; mapping.py + Home mapping components schema-parameterized. Full regression pytest before proceeding.
2. `config/obligation_map.yaml` (~15 entries: CIP-005/007/010/011, TSA SD Pipeline-2021-02F full ID, IEC 62443; generic capability_category + editable Microsoft default_product_label; verification header). `config/product_map.yaml` (products + incumbents alias sections).
3. `core/crosswalk.py`: `gap_table` (landed/partial/gap via product_map), `whitespace_estimate` (gap-category pipeline sum + uncovered-gap list; unresolvables excluded and reported).
4. `core/plan.py` compose; `app/pages/3_Account_Plan.py` (account-facts mapping flow, normalized join w/ fuzzy pick-list confirm that appends alias, whitespace card, .md/.pptx export 4 slides w/ disclaimer).
5. `sample_data/account_facts_sample.csv` (5 accounts incl. all-gap and name-mismatch stress cases); `tests/test_crosswalk.py` per PRD.
   - Verify: refactor regression green; crosswalk tests green; all-gap renders; alias-confirm path appends to aliases.yaml; YAML edit → behavior change without code change.

## Wrap-up
- Final state: `main` holds all four merged sessions, tests green (`pytest` full run), README documents run instructions + data handling.
- Report: files, test results, verification outputs, deviations. Remind user repo is ready to push (`git remote add` + push) when they want.

## Risks
- pandas 3.0 removed several long-deprecated behaviors (e.g., silent downcasting, `read_csv` quirks) — mitigated by explicit parsing everywhere.
- streamlit AppTest can't drive `st.file_uploader` — mitigated per decision 3.
- python-pptx on Python 3.14 untested here — install early in session 3; if broken, pin older or document.
- Windows: no `sqlite3` CLI guaranteed — all DB verification via Python one-liners.
