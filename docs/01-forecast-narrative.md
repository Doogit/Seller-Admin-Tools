---
title: "Tool 1 — Forecast narrative agent"
project: sales-admin-agents
session: 2 of 4
stack: Python, SQLite, Streamlit (inherits foundation)
status: ready-to-run after session 1
depends_on: 00-foundation-ingest-mapping.md
rationale: >
  Sellers spend 30–60 min/week writing commit/upside/risk commentary.
  Deterministic template engine first (works offline, demo-safe, no API key);
  optional LLM polish is a flagged enhancement, not a dependency. Risk rules are
  transparent and editable — a manager must be able to defend every flag.
---

# Implementation: Forecast narrative agent

## Constraints
- Branch required: yes — `feat/forecast-narrative`
- Do not touch: core/ modules except additive helpers; never break Home.py flow.
- Deterministic core: narrative must generate with NO network access and NO API key. LLM polish (if built) is opt-in behind an env var `ANTHROPIC_API_KEY`; absent key = feature hidden, zero errors.
- Output is a draft. Every screen labels it "Draft — review before submitting." Tool never claims to submit anywhere; export is copy-to-clipboard / download .md only.

## Objective
Streamlit page that reads the latest snapshot (plus prior snapshot if present) and drafts the weekly commit / upside / risk narrative with numbers, week-over-week movement, and rule-based risk callouts. Seller edits inline, copies out. Done = narrative generates from sample data in <2s and every number in it traces to a query.

## Context
Load these files in order:
1. core/store.py — snapshot/opportunity schema and query helpers
2. core/schema.py — canonical + optional fields
3. app/Home.py — session-state conventions to reuse

Current state: foundation complete; ≥1 snapshot in agents.db.

## Pre-flight checks
- [ ] `sqlite3 data/agents.db "select count(*) from snapshots"` — expected ≥1. If 0: stop, run Home.py flow first.
- [ ] `pytest tests/` — expected: all pass. If fail: stop and report; do not build on a broken foundation.

## Task 1: analytics module — core/forecast.py
Pure functions, all unit-testable, no Streamlit imports.

### 1A: bucket_rollup(snapshot_id) -> dict
Commit / upside / pipeline totals. Precedence: use forecast_category if mapped; else derive from stage buckets (late→commit-eligible, mid→upside, early→pipeline) and label the page "derived from stage — map forecast_category for accuracy."

### 1B: wow_delta(current_id, prior_id) -> DataFrame
Join precedence: opportunity_id when mapped; else normalized (account_name, opportunity_name) pair. Never match on raw strings. Classify: new, moved stage, amount changed, slipped close_date, disappeared. Rows that fail to match go to an `unmatched` bucket surfaced in the UI ("3 opportunities couldn't be matched to last week — renamed or ID missing?") — never silently classified as new+disappeared, which double-counts movement. Handle missing prior snapshot: return None; page renders without WoW column.

### 1C: risk_flags(snapshot_id) -> DataFrame
Rules in `config/risk_rules.yaml` (thresholds editable, defaults):
- stalled: no stage change observed across snapshot history spanning ≥ 45 days. Stage age = days since the earliest consecutive snapshot showing the current stage (walk snapshots backward per opportunity). NOT created_date — that measures opportunity age and would false-flag deals that advanced recently. If total history spans < 45 days, rule reports "insufficient history (N days observed)" instead of firing or staying silent.
- slipped: close_date moved out ≥1 quarter vs prior snapshot
- no_sponsor: exec_sponsor blank on deals ≥ $500k (skip if field unmapped)
- big_and_late: amount ≥ $1M and close_date within 30 days but stage not late
Each flag row: opportunity, rule name, evidence string ("close date moved 2026-09-30 → 2027-03-31").

## Task 2: narrative engine — core/narrative.py
`draft(rollup, deltas, flags) -> dict{commit, upside, risk}` — three strings, 2–4 sentences each, assembled from templates:
- Commit: total, WoW direction, count of late-stage deals, coverage if quota provided (optional sidebar input, session-only).
- Upside: top 2 movers by amount with what changed.
- Risk: top flags by amount, each with its evidence string; if >3 flags, summarize remainder as a count.
Templates live in `config/narrative_templates.yaml` so wording is editable without code. No adjectives without data behind them.

## Task 3: Streamlit page — app/pages/1_Forecast_Narrative.py
1. Snapshot selector (default latest) + prior-snapshot selector (default previous).
2. Metric cards: commit, upside, coverage (if quota entered), at-risk total.
3. Three editable text_areas pre-filled from narrative.draft, section-colored (commit/upside/risk).
4. Risk table below with evidence strings (this is the manager coaching view).
5. Export: render the assembled narrative in an `st.code` block (built-in copy button — no custom clipboard JS/components) + Download .md button. Regenerate re-runs draft and discards edits after an explicit confirm.
6. Footer note: "Draft — review before submitting. Read-only: nothing is sent anywhere."

## Task 4: tests
tests/test_forecast.py: rollup math on sample snapshot; wow_delta matches on opportunity_id when a name changed between snapshots (renamed opp = "moved/changed", not new+disappeared); unmatched bucket populated when ID absent and names diverge; wow_delta detects a slipped deal (second synthetic snapshot in-test); stalled rule fires only with ≥45-day same-stage history and reports insufficient-history below that; each other risk rule fires on a crafted row and stays silent otherwise; narrative.draft output contains the rollup numbers verbatim.

## Verification checklist
- [ ] `pytest tests/test_forecast.py` → all pass
- [ ] `streamlit run app/Home.py` → page 1 renders from sample snapshot in <2s
- [ ] Traceability: pick any dollar figure in the drafted narrative → matches `sqlite3` query against opportunities for that snapshot
- [ ] Missing-optional-field degradation: create profile mapping only required fields → page renders, sponsor rule skipped with visible note, no traceback
- [ ] Offline: disconnect network → full generation works
- [ ] Renamed-opp integrity: rename one opp in a copy of the sample CSV (same opportunity_id), import as new snapshot → WoW shows it as changed, not new+disappeared; totals move by $0
- [ ] st.code block renders full narrative with working copy affordance; downloaded .md contains all three sections

## Final output
Files changed, test results, verification outputs with actual values, branch + PR link, next step.

## Handoff to next session
Next session: 02-qbr-assembler.md.
Needs from this session: forecast.py rollup/delta functions (QBR reuses them), ≥2 snapshots in agents.db for WoW demo.
Start next session by reading core/forecast.py.
