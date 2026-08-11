# Handover — sales-admin-agents (all 4 PRDs implemented, final review pending)

## Prompt for a new session

> Read `docs/HANDOVER.md`, `docs/PLAN.md`, and the four PRDs in `docs/` for
> context. All four sessions are implemented, tested, and merged to local
> `main` (68 tests passing; repo has NO remote — do not push until told).
> The one remaining task: run `compound-engineering:ce-code-review` to
> convergence over the changes since the session-1 review, i.e.
> `base:8717981` (everything after the session-1 fix commit: sessions 2–4 —
> core/forecast.py, core/narrative.py, core/formatting.py, core/deck.py,
> core/styles.py, core/crosswalk.py, core/plan.py, schema-parameterization
> refactor, app/ui.py, app/pages/1–3, configs, tests). Interactive mode:
> apply safe verified fixes, run `python -m pytest tests/` after each round,
> commit fixes as `fix(review): ...` on a branch merged to main, and repeat
> the review until a pass yields no actionable P0/P1 findings. Session-1 code
> was already reviewed by a 7-agent pipeline and its findings applied in
> commit 8717981 — do not re-review it except where sessions 2–4 touch it.
> After convergence, give a final report (files, test results, verification
> outputs, deviations) and remind me the repo is ready to push.

## State

- **Repo**: `C:\Users\JustD\Documents\GitHub\seller-admin-tools`, git on `main`
  at `154fa08`, no remote, working tree clean. Feature branches
  (`feat/foundation-ingest`, `feat/forecast-narrative`, `feat/qbr-assembler`,
  `feat/account-plan`) all merged --no-ff; safe to delete or keep.
- **Env**: Python 3.14.3; pinned in requirements.txt: streamlit 1.57.0,
  pandas 3.0.3, PyYAML 6.0.3, python-pptx 1.0.2, pytest 9.0.3. All installed.
- **Tests**: `python -m pytest tests/` → 68 passed (~8s). Tests use tmp DBs.
- **Demo DB**: `data/agents.db` (git-ignored) seeded with snapshots wk25
  (as-of 49 days back, mutated prior week) and wk32 (sample as-is) via
  `python sample_data/seed_snapshots.py`, plus 5 account-facts rows. Reseed
  anytime: delete `data/agents.db`, run the seed script, then re-import facts
  (`core.importer.import_account_facts` with suggested mapping — see
  tests/test_crosswalk.py fixtures).
- **Run the app**: `streamlit run app/Home.py`. Demo order per PRD 03: Home
  mapping screen → Forecast Narrative → QBR download → Account Plan gap table.

## What was done (chronological commits on main)

1. `7d35b0c` docs: four PRDs + PLAN.md v1
2. `a3e3a94` PLAN.md v2 — integrated three plan-review agents' findings
   (shared `core/importer.py`, `as_of_date` time model, row-level wow_delta
   semantics, frozen full-arc sample CSV, three-branch auto date rule,
   db_path test isolation, restored PRD verification items)
3. `588c048`/`679b192` session 1 foundation (see PRD 00)
4. `2962c68`/`37c9581` session 2 forecast narrative (PRD 01)
5. `8717981` fix(review): 7-agent ce-code-review of session 1; applied 1 P1
   (Home dup-override rerun bug), 4 P2 (atomic import, euro-decimal
   corruption, cp1252 fallback, day>31 date evidence), 6 P3, +9 tests
6. `20baca0`/`2e35abe` session 3 QBR assembler (PRD 02)
7. `a9ba067` schema-parameterized mapping refactor (PIPELINE_SCHEMA /
   ACCOUNT_SCHEMA; zero test changes)
8. `a8f2fe8`/`154fa08` session 4 account plan generator (PRD 03)

## Key design decisions (details in docs/PLAN.md)

- One monorepo by PRD design; per-PRD separation via `core/` module +
  `app/pages/N_*.py` + `tests/test_*.py` + one branch/merge per session.
- All imports (UI and seeds) go through `core/importer.py` → snapshots are
  structurally identical regardless of entry point.
- `snapshots.as_of_date` (not `imported_at`) drives stalled-rule stage-age
  math; seeds backdate the prior week 49 days.
- wow_delta matching is row-level: non-empty opportunity_id joins on ID
  (residual = trusted new/disappeared); ID-less rows join on normalized
  names (residual = `unmatched` bucket, never new+disappeared).
- Deck/narrative share `core/forecast` + `core/formatting.fmt_money`; the
  consistency-guard test parses the commit figure back out of the built pptx.
- Config-not-code: stage_map, aliases, risk_rules, narrative_templates,
  obligation_map (15 entries, disclaimer header), product_map — all editable
  YAML, read at call time.
- Verification-generated YAML/DB mutations are reverted before merging.

## Known deferred items (deliberate, do NOT build without asking)

- PRD 03 backlog: manager roll-up page, branded pptx template, LLM polish
  behind ANTHROPIC_API_KEY, real MSX header profile.
- Advisory review findings consciously skipped: case-variant stage collision
  warning; explicit "update existing profile" confirm (mitigated by
  stage-assignment merge); mapping.save_profile thin wrappers (intended seam).
- Browser-only checks left for a human at demo time: physical drag-drop
  upload and download-button clicks (everything behind them is
  AppTest/pytest-verified).

## User instructions in force

- No push to GitHub until the user says so (repo has no remote yet).
- Concise, no emojis, no trailing summaries; surgical changes; simplicity
  first (see user CLAUDE.md).
- Final ce-code-review to convergence was explicitly requested by the user —
  it is the agreed next step.
