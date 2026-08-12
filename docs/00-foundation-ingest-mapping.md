---
title: "Sales Admin Agents — Foundation: CSV ingest + column mapping"
project: sales-admin-agents
session: 1 of 4
stack: Python 3.11+, SQLite, Streamlit, pandas
status: ready-to-run
depends_on: none
rationale: >
  CRM export schemas are not publicly documented. Design decision:
  never hard-code source column names. All tools reference a canonical schema;
  a user-facing mapping screen translates any CSV export to canonical fields.
  Schema incompatibility becomes a 30-second remap, not a rebuild.
---

# Implementation: Foundation — CSV ingest + column-mapping layer

## Constraints
- Branch required: yes — `feat/foundation-ingest`
- READ-ONLY posture: no writes to any external system, no network calls, no telemetry. All data stays local (SQLite file + session state).
- Vendor-neutral: no CRM-specific column names anywhere in core logic. sales-stage labels live in a config file, not code.
- No auth, no multi-user. Single-operator local tool.
- Do not install heavyweight deps. Allowed: streamlit, pandas, pyyaml. Nothing else without documenting why. Pin exact versions in requirements.txt (demo-stability guarantee).
- Confidentiality (runtime, not just repo): This repo ships fictional data only. Any real CRM exports and data/agents.db live only on the operator's own machine and are never committed. State this in README under "Data handling."
- Single-currency assumption (USD): strip symbols/separators; mixed-currency detection is out of scope v1 — if multiple currency symbols detected in the amount column, warn and proceed.

## Objective
Scaffold the `sales-admin-agents` monorepo and build the shared ingestion + column-mapping module that Tools 1–3 (QBR assembler, account plan generator, forecast narrative) will import. Done = a Streamlit page that accepts any pipeline CSV, walks the user through mapping columns to the canonical schema, persists the mapping as a reusable profile, and stores normalized rows in SQLite.

## Context
Greenfield. No files to load. Reference pattern: the pipeline-hygiene agent (CSV-ingestion-first, read-only, Python/SQLite/Streamlit).

Current state:
- Nothing exists. This session creates the repo.

## Canonical schema (v1)
Required fields (mapping screen must resolve all of these):

| canonical field | type | notes |
|---|---|---|
| account_name | str | |
| opportunity_name | str | |
| stage | str | raw value; normalized via stage_map |
| amount | float | strip $ , () |
| close_date | date | parse common formats |
| owner | str | seller alias/name |

Optional fields (mapping screen offers them; tools degrade gracefully if absent):

| canonical field | type | used by |
|---|---|---|
| opportunity_id | str | join key for WoW deltas — strongly recommend mapping; CRM exports nearly always have one |
| forecast_category | str (commit/upside/pipeline) | Tools 1, 3 |
| probability | float 0–100 | Tools 1, 3 |
| last_activity_date | date | Tool 3 risk detection |
| product | str | Tools 1, 2 |
| sub_vertical | str (power & utilities / oil & gas / pipelines) | Tools 1, 2 |
| exec_sponsor | str | Tool 3 risk detection |
| created_date | date | stage-aging calc |

Stage normalization: `config/stage_map.yaml` maps raw stage strings → canonical buckets `early | mid | late | closed_won | closed_lost`. Ship a default with generic labels AND common numbered enterprise-stage labels (01 Inspire, 02 Design, 03 Empower, 04 Achieve, 05 Realize) as examples. Unmapped stages surface in the UI for one-click assignment; assignments persist to the profile.

## Repo layout to create
```
sales-admin-agents/
  README.md
  requirements.txt
  config/stage_map.yaml
  config/aliases.yaml   # owner + account name normalization: canonical -> [aliases]
  core/
    __init__.py
    schema.py        # canonical field definitions + validators
    ingest.py        # CSV load, type coercion, cleaning
    mapping.py       # header auto-suggest + profile save/load
    store.py         # SQLite: snapshots, mapping_profiles tables
  app/
    Home.py          # Streamlit entry: upload → map → confirm → save snapshot
    pages/           # empty; tools 1–3 add pages here
  sample_data/
    energy_pipeline_sample.csv   # 40 fictional rows, energy accounts, numbered enterprise stages
  tests/
    test_mapping.py
    test_ingest.py
```

## Pre-flight checks
Run before writing code. If a check fails: stop and report.
- [ ] `python --version` — expected: 3.11+
- [ ] `pip install streamlit pandas pyyaml` — expected: success
- [ ] Working directory is empty or new repo dir — expected: no existing sales-admin-agents/ to avoid clobbering

## Task 1: Core modules
### 1A: schema.py
Define `REQUIRED_FIELDS`, `OPTIONAL_FIELDS` as dicts {name: {type, description}}. Provide `validate_frame(df) -> list[str]` returning human-readable problems (missing required, unparseable dates, negative amounts).

### 1B: ingest.py
`load_csv(file) -> pd.DataFrame` — tolerate BOM, semicolon delimiters, thousands separators, ($1,234.00) negatives. Date parsing takes an explicit `date_format` argument (`auto | mdy | dmy | iso`) — NEVER bare to_datetime coercion, which silently misreads 03/04/2026 depending on locale. `auto` samples the column: if any value is unambiguous (day > 12), infer; if all values are ambiguous, force the user to choose on the mapping screen. Report coercion failures, don't silently drop.
Also `normalize_name(s, aliases) -> str` — lowercase, strip punctuation/suffixes (Inc, Corp, LLC), then alias lookup from config/aliases.yaml. Used for owner and account_name at import time; raw value preserved in a `_raw` column.

### 1C: mapping.py
- `suggest_mapping(headers: list[str]) -> dict[canonical, source|None]` — fuzzy match (lowercase, strip punctuation, synonym table: e.g. amount ~ ["est. revenue","opportunity revenue","acr","value","amount"]). Suggestions only; user confirms everything.
- `save_profile(name, mapping, stage_assignments)` / `load_profiles()` via store.py.

### 1D: store.py
SQLite at `data/agents.db`. Tables (idempotent `CREATE TABLE IF NOT EXISTS`):
- `mapping_profiles(id, name, created_at, mapping_json, stage_map_json)`
- `snapshots(id, imported_at, profile_id, label, file_sha256)` — label e.g. "wk32". On import, if file_sha256 matches an existing snapshot, warn ("already imported as <label> on <date>") and require explicit override — prevents phantom weeks and zeroed deltas. Index on opportunities(snapshot_id).
- `opportunities(snapshot_id, <canonical columns>)` — one row per opp per snapshot. Snapshots are append-only; never mutate a prior snapshot (week-over-week deltas in Tools 1 and 3 depend on this).

## Task 2: Streamlit Home.py — the mapping screen
Flow (single page, top to bottom, no tabs):
1. File uploader + profile selector ("New mapping" or saved profile).
2. On upload: show detected headers + 5-row preview.
3. Mapping grid: one row per canonical field — field name, description, selectbox of source columns (pre-selected from suggest_mapping), live sample values from the chosen column. Required fields flagged; Confirm disabled until all required are mapped.
4. Date format selector (auto/US/intl/ISO) with a live preview of 3 parsed sample dates so the user can catch a misparse before import; choice persists to the profile.
5. Stage assignment: distinct raw stage values with bucket selectboxes; pre-fill from stage_map.yaml; unknowns highlighted.
6. Validation results from validate_frame; blocking errors vs warnings.
7. Confirm → save profile (prompt for name) → write snapshot (prompt for label, default ISO week; duplicate-hash warning per store.py) → success summary: N rows, M accounts, total pipeline $.

## Task 3: Sample data + tests
- Generate `sample_data/energy_pipeline_sample.csv`: 40 rows, fictional energy accounts (utilities, oil & gas, pipeline operators), deliberately messy headers ("Est. Revenue", "Close Dt", "Sales Stage"), an Opportunity ID column, numbered enterprise-stage labels, 2 unmapped stage values, 1 malformed date, 1 all-ambiguous date pair (03/04/2026), 1 negative amount, and one account appearing as both "Meridian Energy" and "Meridian Energy Corp" — so the demo shows the tool catching every failure class.
- Ship config/aliases.yaml pre-seeded for the sample's Meridian variant.
- tests: suggest_mapping resolves the sample headers; ingest coerces amounts; mdy vs dmy produce different (correct) dates for the ambiguous row; normalize_name unifies the Meridian variants; store round-trips a snapshot; duplicate hash raises the warning path.

## Verification checklist
- [ ] Mapping suggestions: `pytest tests/test_mapping.py` → all pass
- [ ] Ingest coercion: `pytest tests/test_ingest.py` → all pass
- [ ] End-to-end: `streamlit run app/Home.py`, upload sample CSV, complete mapping, save snapshot → success summary shows 40 rows and flags the malformed date + negative amount
- [ ] Persistence: `sqlite3 data/agents.db "select count(*) from opportunities"` → 40
- [ ] Profile reuse: re-upload same CSV, pick saved profile → mapping + date format pre-filled, duplicate-hash warning shown, zero manual selections needed
- [ ] Alias normalization: post-import, `sqlite3 data/agents.db "select count(distinct account_name) from opportunities"` counts Meridian once
- [ ] Grep guard: `grep -ri "vendor-crm-name" core/ app/` → no matches (vendor neutrality)

## Final output
Return: files created, test results, verification outputs, branch + PR link, any deviations with rationale.

## Handoff to next session
Next session: 01-forecast-narrative.md (simplest tool; exercises the foundation).
Needs from this session: working Home.py flow, saved profile + at least one snapshot in agents.db, sample CSV path.
Start next session by reading core/schema.py and core/store.py.
