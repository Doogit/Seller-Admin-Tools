---
title: "Tool 3 — Account plan generator"
project: sales-admin-agents
session: 4 of 4
stack: Python, SQLite, Streamlit (inherits foundation + deck.py export pattern)
status: ready-to-run after session 3
depends_on: 02-qbr-assembler.md
rationale: >
  Account plans are a mandatory recurring artifact whose skeleton sellers rebuild
  every cycle. Differentiator vs. generic plan tools: the obligation → capability →
  gap crosswalk (NERC CIP / TSA SD → security product families) generated from a
  maintained reference table. Crosswalk reference data is generic-capability-labeled
  and user-editable YAML — vendor-neutral core, vendor labels are just the
  shipped default config.
---

# Implementation: Account plan generator

## Constraints
- Branch required: yes — `feat/account-plan`
- Second input type: account-facts CSV (distinct from pipeline CSV). It gets its own canonical schema + mapping flow — REUSE core/mapping.py and the Home.py mapping components; do not fork a second mapping implementation. If reuse requires refactoring mapping.py to be schema-parameterized, do that refactor first with tests.
- Crosswalk reference lives in `config/obligation_map.yaml` — data, not code. No regulatory text reproduced beyond requirement IDs + short paraphrase (one line each, own words).
- Read-only, local-only, fictional sample data only.

## Objective
Streamlit page: upload/select account facts, join with pipeline snapshot for that account, generate an structured account plan on screen with an obligation → capability → gap table, export .md and .pptx. Done = plan for a sample utility account generates in one click and the gap table drives a whitespace dollar estimate.

## Context
Load in order:
1. core/mapping.py + core/schema.py — assess what refactor is needed for a second schema
2. core/store.py — add account_facts table
3. core/deck.py + app/ui.py — export + render patterns

Current state: sessions 1–3 complete.

## Canonical account-facts schema (v1)
Required: account_name, sub_vertical. Optional: annual_spend, agreement_end_date, install_base (semicolon-delimited product list), incumbent_tools (semicolon list), known_gaps (semicolon list of obligation IDs or free text), exec_contacts, regulatory_scope (semicolon list: NERC_CIP, TSA_SD, IEC_62443, state_puc).

## Pre-flight checks
- [ ] `pytest tests/` — all pass, else stop.
- [ ] `grep -c "obligation" core/*.py` — expected 0 (confirm crosswalk not yet implemented anywhere; avoids duplicate logic).

## Task 1: schema-parameterized mapping refactor
Make schema.py expose `PIPELINE_SCHEMA` and `ACCOUNT_SCHEMA` objects; mapping.py and the Home mapping UI components take a schema argument. Regression: existing pipeline flow and all prior tests still pass unchanged. This is the riskiest task — do it first, verify, commit separately.

## Task 2: crosswalk data + engine
### 2A: config/obligation_map.yaml
Structure per entry: obligation_id (e.g. CIP-007-6), framework, one-line paraphrase, capability_category (generic: endpoint_protection, siem, identity, ot_security, data_protection, patch_mgmt), default_product_label (shipped default: example vendor product names — Defender for Cloud, Sentinel, Entra, Defender for OT, Purview; editable). Ship ~15 entries covering CIP-005/007/010/011, TSA Security Directive Pipeline-2021-02F (use the full directive ID in the data — practitioners will notice shorthand), IEC 62443 top-level. Mark file header: "Reference data — verify against current standard text before customer use."

### 2B: config/product_map.yaml
Free-text → capability_category resolver. Two sections: `products` (pipeline `product` values and install_base entries → category; ship aliases for common labels, e.g. "sentinel", "siem", "microsoft sentinel" → siem) and `incumbents` (competitor tool names → category, e.g. "splunk" → siem). Matching: case-insensitive substring against alias lists; unresolved values collect into an `unmapped` list surfaced in the UI with a one-click "assign category" control that appends to the YAML. Without this file the whitespace math and partial-status detection cannot work — pipeline products and crosswalk categories otherwise never connect.

### 2C: core/crosswalk.py
`gap_table(account_row, install_base) -> DataFrame` — for each obligation in the account's regulatory_scope: required capability, matching product label, status ∈ {landed, partial, gap}. Status resolution goes through product_map: landed = any install_base entry resolves to the obligation's capability_category; partial = no install match but an incumbent_tools entry resolves to it (displace play); else gap. `whitespace_estimate(gap_df, pipeline_df)` — sum of open pipeline whose product resolves (via product_map) to a gap category + count of uncovered gaps with zero pipeline (the "no play exists yet" list — arguably the most valuable output). Unresolvable products are excluded from the estimate and reported, never guessed.

## Task 3: plan composer — core/plan.py
`compose(account, gaps, pipeline) -> dict` with sections: account summary; current footprint; obligation gap table; open pipeline for account; whitespace + uncovered gaps; Next actions (rule-based: gap+no pipeline → "Inspire/Design play", partial → "displacement play at Empower", landed → "expand/Realize"); relationship map placeholder (human section, like QBR asks).

## Task 4: Streamlit page — app/pages/3_Account_Plan.py
1. Account-facts upload with mapping flow (schema-parameterized components) OR pick previously imported account. Account names normalized at import via ingest.normalize_name + config/aliases.yaml — same path as pipeline imports.
2. Account selector → plan preview using ui.py components; gap table color-coded landed/partial/gap. Facts↔pipeline join runs on normalized account_name; if an account matches zero pipeline rows, show a warning with a fuzzy-suggested pick-list of near-name pipeline accounts and require an explicit confirm (which appends the alias to aliases.yaml) rather than rendering a silently empty pipeline section.
3. Whitespace metric card + "uncovered gaps" callout list.
4. Downloads: .md and .pptx (reuse deck.py pattern; slides: summary, gap table, pipeline+whitespace, next actions).
5. Footer: crosswalk-verification disclaimer from the YAML header.

## Task 5: sample data + tests
`sample_data/account_facts_sample.csv` — 5 fictional energy accounts, varied regulatory_scope and install bases, including one with zero install base (all-gap stress case) and one whose name differs from its pipeline spelling (join stress case). tests/test_crosswalk.py: landed/partial/gap classification via product_map aliases; whitespace math excludes an unresolvable product and reports it; empty install base; unknown obligation ID in known_gaps → warning not crash; incumbent "Splunk" yields partial on the SIEM obligation.

## Verification checklist
- [ ] Task 1 regression: `pytest tests/` after refactor, before new features → all pass
- [ ] `pytest tests/test_crosswalk.py` → all pass
- [ ] Page 3: sample utility account → plan renders; gap table shows all three statuses; whitespace figure matches manual sum of gap-category pipeline
- [ ] All-gap account renders without traceback
- [ ] Mismatched-name account triggers the pick-list confirm; after confirm, aliases.yaml contains the new alias and the plan shows pipeline rows
- [ ] Add a nonsense product to sample pipeline → whitespace excludes it and the unmapped list shows it with the assign-category control
- [ ] Edit obligation_map.yaml or product_map.yaml → rerun → change appears (no code change needed)
- [ ] .pptx opens with 4 slides and disclaimer present

## Final output
Files changed, test results, verification outputs, branch + PR link.

## Handoff
Project complete for MVP scope. Post-validation backlog (do NOT build now):
- Manager roll-up page (owner_rollup already tested in forecast.py)
- Branded pptx template via styles.py
- Optional LLM narrative polish behind ANTHROPIC_API_KEY
- Real CRM header mapping profile — create once actual export column headers are available (headers only, never data)
Demo order for interviews: Home mapping screen → Forecast Narrative → QBR download → Account Plan gap table.
