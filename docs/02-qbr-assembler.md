---
title: "Tool 2 — ROB/QBR deck assembler"
project: sales-admin-agents
session: 3 of 4
stack: Python, SQLite, Streamlit, python-pptx (inherits foundation)
status: ready-to-run after session 2
depends_on: 01-forecast-narrative.md (reuses core/forecast.py)
rationale: >
  The recurring business review is the single biggest recurring deck-build tax.
  Reuse forecast.py analytics so QBR numbers ALWAYS match the weekly narrative —
  one source of truth, two artifacts. MVP export is .pptx with a plain built-in
  template; team-branded templates are a post-validation polish step per the
  iterative MVP principle.
---

# Implementation: ROB/QBR deck assembler

## Constraints
- Branch required: yes — `feat/qbr-assembler`
- Reuse core/forecast.py for all rollups/deltas. Do NOT re-implement pipeline math; if QBR needs a new metric, add it to forecast.py with tests.
- New dependency allowed: python-pptx only.
- Read-only posture unchanged. Export = local .pptx / .md download.
- Sample output must contain fictional data only; README warns never to commit real exports (add `sample_data/` exception, ignore `data/` and `*.csv` at root in .gitignore — verify session 1 did this; if not, fix here).

## Objective
Streamlit page that turns selected snapshot(s) into a review package: on-screen QBR view + downloadable .pptx (5 slides) + .md appendix. Done = one click from snapshot to a deck a seller could present with ≤5 minutes of personal edits.

## Context
Load in order:
1. core/forecast.py — rollup, wow_delta, risk_flags signatures
2. core/store.py — snapshot queries
3. app/pages/1_Forecast_Narrative.py — page conventions

Current state: sessions 1–2 complete; ≥2 snapshots exist.

## Pre-flight checks
- [ ] `sqlite3 data/agents.db "select count(*) from snapshots"` — expected ≥2. If 1: generate a second synthetic snapshot from sample data with a documented mutation script in `sample_data/make_prior_snapshot.py`; do not fake it silently.
- [ ] `pytest tests/` — all pass, else stop.
- [ ] `pip install python-pptx` — success.

## Task 1: QBR analytics additions — extend core/forecast.py
- `stage_distribution(snapshot_id)` — count + $ per stage bucket, with WoW deltas.
- `top_deals(snapshot_id, n=10)` — by amount, with stage, close_date, owner, flags joined.
- `owner_rollup(snapshot_id)` — per-seller commit/upside/at-risk (feeds the manager roll-up later; build it now, cheap). Group on the alias-normalized owner field from ingest — a seller appearing as "K. Dugas" and "Kevin Dugas" must roll up as one row; add a test with alias variants.
- `sub_vertical_split(snapshot_id)` — power & utilities / oil & gas / pipelines totals; graceful skip if field unmapped.
Tests for each in tests/test_forecast.py.

## Task 2: deck builder — core/deck.py
`build_pptx(snapshot_id, prior_id, meta) -> BytesIO` using python-pptx, plain white template, five slides:
1. Title: period label, team/segment name (user input), generated date, "DRAFT" footer.
2. Scorecard: commit / upside / coverage / at-risk as a 2x2 table + WoW arrows.
3. Stage movement: native pptx bar chart from stage_distribution (no image screenshots).
4. Top deals: table capped at 10 rows, 5 columns max (opp, account, stage, amount, close), fixed 10–11pt font, opportunity names truncated at ~40 chars with ellipsis — pptx tables silently overflow the slide otherwise.
5. Risks & asks: flag evidence strings as bullets + empty "Asks" placeholder box (the one section that must stay human).
Also `build_md(...)` mirroring the same content for the appendix.
All text through one `styles.py` constant block so template polish later is one-file work.

## Task 3: Streamlit page — app/pages/2_QBR_Assembler.py
1. Inputs: snapshot, prior snapshot, period label, team name, optional quota.
2. Preview: metric cards, stage bars, top-deals table, risk list (reuse page-1 components where possible; extract shared render helpers to app/ui.py rather than copy-paste).
3. Downloads: .pptx and .md. Filenames `qbr_<period>_<yyyymmdd>.pptx`.
4. Note: "Numbers identical to Forecast Narrative for the same snapshot."

## Task 4: consistency guard test
tests/test_deck.py: build pptx from sample snapshot; open it with python-pptx; extract the slide-2 commit figure, parse it back to a number (strip $, M/K suffix), and assert numeric equality with forecast.bucket_rollup within rounding tolerance of the display precision. Compare values, not formatted strings — a formatting tweak must not break the test while a wrong number must. This is the "deck never disagrees with the narrative" contract.

## Verification checklist
- [ ] `pytest tests/` → all pass including consistency guard
- [ ] Page 2 renders and both downloads succeed from sample data
- [ ] Open the .pptx in a viewer: 5 slides, chart renders, DRAFT footer present
- [ ] Same snapshot on page 1 and page 2 → identical commit/upside/at-risk figures
- [ ] Unmapped sub_vertical profile → deck builds without vertical split, visible note, no traceback
- [ ] `git check-ignore data/agents.db` → ignored

## Final output
Files changed, test results, verification outputs, branch + PR link, next step.

## Handoff to next session
Next session: 03-account-plan-generator.md.
Needs from this session: app/ui.py shared render helpers, owner_rollup (unused by Tool 3 but confirm it's tested), deck.py styles pattern (account plan export copies it).
Start next session by reading core/deck.py and app/ui.py.
