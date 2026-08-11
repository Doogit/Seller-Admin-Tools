# Execution plan — sales-admin-agents (4 PRDs) — v2, post-review

Source PRDs: `docs/00-foundation-ingest-mapping.md` → `docs/03-account-plan-generator.md`.
Goal: implement all four sessions to first-version quality, locally, with git history per session. No push to GitHub until all four tools exist (user instruction).

v2 integrates findings from three independent plan reviews (feasibility, scope, adversarial). Changelog at bottom.

## Environment facts (verified)
- Python 3.14.3, pip 26.0.1, git 2.53. Installed & verified: streamlit 1.57.0, pandas 3.0.3, PyYAML 6.0.3, pytest 9.0.3, python-pptx 1.0.2.
- **python-pptx spike passed**: one-slide deck with native COLUMN_CLUSTERED chart built, saved, re-read on Python 3.14 — chart path confirmed; no fallback needed.
- Repo initialized: `git init -b main`, docs committed.

## Key decisions / deviations from PRD letter
1. **Repo root = `seller-admin-tools/`** (the existing directory that already holds the PRDs), not a nested `sales-admin-agents/`. PRD layout is created at repo root.
2. **Git flow**: each session on its PRD-mandated branch, merged `--no-ff` to local `main` when its checklist passes. **No remote, no push, no PR links** — replaced by merge commits until the user says push.
3. **Shared import orchestration (new, from review)**: `core/importer.py` exposes `import_snapshot(file, mapping, date_format, stage_assignments, label, as_of_date, on_duplicate) -> ImportResult`. Home.py, `sample_data/seed_snapshots.py`, and `sample_data/make_prior_snapshot.py` ALL call it — seeded snapshots are structurally identical to UI-imported ones, not asserted-identical. Specced behavior: unparseable dates → row stored with NULL date + warning in ImportResult; `on_duplicate` ∈ {`ask` (UI), `skip` (seeds), `override`}. Home.py is a thin wrapper.
4. **Headless verification protocol**:
   - Core logic in `core/` pure functions covered by pytest.
   - Streamlit pages structured so mapping grid / date selector / stage assignment / render sections are functions taking a DataFrame (upload-independent) — exercised directly or via `AppTest`; this also pre-stages the session-4 schema-parameterization refactor.
   - Known AppTest gaps: `st.file_uploader` and `st.download_button` cannot be driven. Substitutions, explicitly: upload path → `load_csv` + component functions on the sample file; downloads → call `build_pptx`/`build_md`/export functions directly and inspect bytes. **Genuinely unverified by the agent: the physical browser drag-drop and download-click interactions** — left to the user at demo time; everything behind them is executed headlessly.
   - Live smoke run: `streamlit run app/Home.py --server.headless true --server.port <free port>` in background, poll `http://127.0.0.1:<port>/_stcore/health`, check each page URL responds, kill. Never run pytest while the live app holds `data/agents.db` (Windows file locking).
5. **DB/test isolation**: `store.py` takes `db_path` (default anchored to repo root `data/agents.db`, not cwd-relative). All tests use `tmp_path` DBs and tmp copies of any YAML they mutate. Config-mutating functions (alias append, category assign) take the config path as an argument. Verification-generated YAML appends are reverted before each session's merge; `data/agents.db` is git-ignored and never committed.
6. **Snapshot time model (new, from review)**: `snapshots` gets an `as_of_date` column (default = import date, user-settable next to the label prompt). Stage-age / history-span math in the stalled rule uses `as_of_date`, never `imported_at` — otherwise batch-imported weeklies collapse to zero history and the rule can never fire. Insufficient-history is measured **per opportunity** (days that opportunity has been observed), not per DB. Seeds backdate: prior snapshot `as_of_date` ≥46 days back with one opp stage-unchanged (stalled fires, incl. exactly-45-day boundary case in tests), one advanced (silent), one only-in-current (insufficient history).
7. **`wow_delta` semantics pinned (new, from review)**: precedence is **row-level** — rows with non-empty `opportunity_id` join on ID (residual no-match = genuinely `new`/`disappeared`); ID-less rows join on normalized `(account_name, opportunity_name)`; name-join residuals on **either** side go to `unmatched` (contribute to neither new nor disappeared totals; surfaced as a count in the UI). Blank/duplicate IDs flagged at ingest validation. Test the mixed case: some rows with IDs, some blank, in one snapshot pair.
8. **`auto` date format = three branches (new, from review)**: sample ALL mapped date columns jointly (one format per file): (a) unambiguous evidence agreeing → infer; (b) conflicting unambiguous evidence (dmy-only and mdy-only values both present) → hard error listing offending values; (c) all values ambiguous → raise typed `AmbiguousDateFormat`, which Home.py catches to force the user's choice. Dedicated all-ambiguous fixture in tests (the 40-row sample can't reach branch (c) — its 38 unambiguous dates dominate).
9. **Sample CSV specced for the full 4-session arc and frozen at session 1** (any later edit = breaking change requiring full re-seed, because snapshots key on file_sha256). Columns beyond PRD-00 failure classes: `product` (values resolvable via product_map + one deliberate nonsense value), `sub_vertical`, `forecast_category` (partially populated so both rollup precedence branches run), `exec_sponsor` (blank on one ≥$500k row), `last_activity_date`, `created_date`, `opportunity_id` (blank on 2 rows for the mixed wow_delta case).
10. **Hashes at runtime, bytes protected**: `.gitattributes` marks `sample_data/*.csv -text` (byte-stable — BOM and malformed rows are load-bearing); `file_sha256` always computed at runtime, never a pinned literal. `.gitignore` uses root-anchored `/*.csv` (no negation gymnastics) plus `data/`, `__pycache__/`, `.venv/`.
11. **pandas 3.0 notes for implementation**: Copy-on-Write mandatory (no chained assignment); string dtype is `str` not `object`; `($1,234.00)` needs an explicit converter/regex post-parse — `thousands=","` alone won't cover parenthesized negatives. Mixed-currency-symbol detection in the amount column → warn and proceed (PRD 00 constraint).
12. **Offline check**: OS-level network disconnect isn't autonomously safe; substitute a real runtime guard — a test that monkeypatches `socket.socket` to raise on any connection attempt, then runs full narrative generation. Stronger than code inspection, no system changes.
13. **requirements.txt pins the verified versions** (streamlit 1.57.0, pandas 3.0.3, PyYAML 6.0.3, python-pptx 1.0.2, pytest 9.0.3).
14. **No LLM polish, no manager roll-up page, no branded template** — backlog per PRD 03.

## Sequencing (strictly serial by dependency)
Sessions hard-chained: 00 → 01 → 02 → 03. Efficiency comes from within-session batching and the decisions above being settled up front.

### Session 1 — Foundation (branch `feat/foundation-ingest`)
1. Scaffold repo layout per PRD (README with "Data handling" section; .gitignore & .gitattributes per decision 10).
2. `core/schema.py` (field dicts + `validate_frame`), `core/ingest.py` (`load_csv` per decisions 8/11; `normalize_name` + aliases), `core/mapping.py` (`suggest_mapping`, profile save/load), `core/store.py` (`db_path` param; mapping_profiles; snapshots w/ `as_of_date` + file_sha256 dup guard; opportunities append-only + index), `core/importer.py` (decision 3).
3. `config/stage_map.yaml` (generic + MCEM examples), `config/aliases.yaml` (Meridian pre-seeded).
4. `app/Home.py` per PRD steps 1–7, as a thin wrapper over component functions + importer.
5. `sample_data/energy_pipeline_sample.csv` per decision 9 (40 rows, all PRD-00 failure classes + full-arc columns). `sample_data/seed_snapshots.py` — seeds the demo DB via importer with backdated `as_of_date` (decision 6); justified as distinct from tests (tests use tmp DBs; this seeds the demo `data/agents.db` that downstream session pre-flights and the live demo require).
6. Tests `test_mapping.py`, `test_ingest.py` per PRD + all-ambiguous fixture, mixed-currency warning, conflict-error branch. **Profile-reuse test (restored)**: save profile → load → zero re-selections needed to re-import; duplicate-hash triggers the warning path with `on_duplicate='ask'`.
7. Verify: pytest green; seed; SQLite counts via Python (40 rows; Meridian distinct-count = 1); grep guard msx/mssales; headless smoke per decision 4.

### Session 2 — Forecast narrative (branch `feat/forecast-narrative`)
1. `core/forecast.py`: `bucket_rollup` (forecast_category precedence, stage-derived fallback + label), `wow_delta` per decision 7, `risk_flags` via `config/risk_rules.yaml` (stalled per decision 6; slipped; no_sponsor; big_and_late) with evidence strings.
2. `core/narrative.py` + `config/narrative_templates.yaml` — deterministic 3-section draft, numbers verbatim.
3. `app/pages/1_Forecast_Narrative.py` per PRD (selectors, metric cards, editable areas, risk table, `st.code` export + .md download, draft footer).
4. `tests/test_forecast.py` per PRD + mixed-ID wow_delta + 45-day boundary + offline socket-guard test (decision 12).
5. Second seeded snapshot already exists from session 1's backdated seed; verify WoW renders.
6. Verify: pytest; traceability spot-check (narrative $ == DB sum); required-only profile degrades with visible note; headless smoke.

### Session 3 — QBR assembler (branch `feat/qbr-assembler`)
1. Extend `core/forecast.py`: `stage_distribution`, `top_deals`, `owner_rollup` (alias-variant test), `sub_vertical_split` (graceful skip). Tests.
2. `core/deck.py` (`build_pptx` 5 slides per PRD — native bar chart, capped/truncated table, DRAFT footer; `build_md`), `core/styles.py`.
3. `app/ui.py` shared render helpers extracted from page 1; `app/pages/2_QBR_Assembler.py`.
4. `sample_data/make_prior_snapshot.py` (PRD-mandated; calls importer) — only if a suitable prior snapshot isn't already seeded.
5. `tests/test_deck.py` consistency guard: locate the commit cell **by label text**, strip WoW arrows, parse; assert equality with `bucket_rollup` passed through the same format→parse pair (tolerance 0 after shared formatting, not display-precision slack).
6. Verify: pytest incl. guard; pptx re-read (5 slides, chart, DRAFT footer); page1 vs page2 same-snapshot figures identical; `git check-ignore data/agents.db`; headless smoke.

### Session 4 — Account plan (branch `feat/account-plan`)
0. Pre-flight (restored): `pytest` green; grep `obligation` in `core/*.py` → 0 matches.
1. **Refactor first, commit separately**: `schema.py` → `PIPELINE_SCHEMA`/`ACCOUNT_SCHEMA`; mapping.py + mapping components schema-parameterized. Full regression before proceeding.
2. **`store.py`: add `account_facts` table (restored from PRD)** — replace-latest-by-account semantics (facts are current state, not history); round-trip test. Import path via importer/mapping reuse; page offers "pick previously imported account."
3. `config/obligation_map.yaml` (~15 entries: CIP-005/007/010/011, TSA SD Pipeline-2021-02F full ID, IEC 62443; generic capability_category + editable MS default labels; verification header). `config/product_map.yaml` (products + incumbents alias sections; append functions take path arg).
4. `core/crosswalk.py`: `gap_table` (landed/partial/gap via product_map), `whitespace_estimate` (gap-category pipeline sum + uncovered-gaps list; unresolvables excluded and reported).
5. `core/plan.py` compose; `app/pages/3_Account_Plan.py` (account-facts mapping flow, normalized join w/ fuzzy pick-list confirm appending alias, whitespace card, .md/.pptx export via deck pattern).
6. `sample_data/account_facts_sample.csv` (5 accounts incl. all-gap and name-mismatch); `tests/test_crosswalk.py` per PRD.
7. Verify: refactor regression; crosswalk tests; all-gap renders; alias-confirm appends (then revert demo mutation); nonsense product excluded + surfaced; YAML edit → behavior change; **pptx re-read: 4 slides + disclaimer text present (restored)**; headless smoke.

## Wrap-up
- Final state: `main` holds four merged sessions, full `pytest` green, README documents run instructions + data handling.
- Report: files, test results, verification outputs, deviations. Repo ready to push when the user says so.

## Review changelog (v1 → v2)
Accepted: shared importer (adversarial #3); as_of_date time model + per-opp history + boundary test (adversarial #4); row-level wow_delta semantics + mixed-ID test (adversarial #1); full-arc frozen sample CSV (adversarial #2); three-branch auto date rule + typed exception + fixture (adversarial #5, feasibility #10); consistency-guard label-lookup + format→parse equality (adversarial 2nd); db_path/test isolation + YAML path params (adversarial 2nd, feasibility #5); root-anchored gitignore + .gitattributes + runtime hashing (adversarial 2nd, feasibility #6); headless streamlit protocol (feasibility #3); upload-independent components (feasibility #4a, scope #2); account_facts store (feasibility #2); mixed-currency warning (feasibility #7); pandas 3.0 notes (feasibility #8); pptx spike done up front (feasibility #1 — passed); profile-reuse verification (scope #1); session-4 pptx structural verify (scope #3); grep-obligation pre-flight (scope #4); pytest version verified (feasibility #9).
Modified: offline check done as socket-guard runtime test, not OS disconnect (scope #6 — OS-level network toggling isn't autonomously safe).
Rejected: cutting `seed_snapshots.py` (scope #5) — tests use tmp DBs, but downstream pre-flights and the live demo need the real `data/agents.db` seeded reproducibly; kept with explicit justification and shared-importer implementation.
