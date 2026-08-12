# Seller Admin Tools

A local, read-only toolkit that turns a weekly CRM pipeline export into the
administrative artifacts an enterprise seller produces by hand every week:
a forecast narrative, a QBR deck, and an account plan.

Everything runs on one machine. **No authentication, no network calls, no
telemetry** — data lives in a local SQLite file and Streamlit session state, and
every export is a local file download. The tools never write back to any CRM or
external system.

- **Vendor-neutral core.** No CRM-specific column names are hard-coded anywhere.
  A mapping screen translates *any* CSV export to a canonical schema, so a new
  export format is a 30-second remap, not a code change.
- **Deterministic.** Given the same snapshot, every tool produces byte-identical
  output. The QBR deck and the forecast narrative read the same analytics
  functions, so their numbers can never disagree.
- **Config-not-code.** Stage maps, name aliases, risk rules, narrative templates,
  and the compliance crosswalk all live in editable YAML under `config/`, read
  at call time.

---

## The four tools

| # | Tool | Input | Output |
|---|------|-------|--------|
| 0 | **Home / Ingest** | Any pipeline CSV export | A saved, reusable column-mapping profile + a stored snapshot |
| 1 | **Forecast Narrative** | A snapshot (+ the prior week) | Commit/upside/risk narrative with week-over-week movement, `.md` export |
| 2 | **QBR Assembler** | A snapshot (+ the prior week) | A 5-slide `.pptx` deck + `.md` appendix |
| 3 | **Account Plan** | Account-facts CSV + a snapshot | An account plan with a compliance gap crosswalk + whitespace estimate, `.pptx`/`.md` |

### 0. Home — ingest & column mapping

![Home — pipeline import and column mapping](docs/screenshots/0-home-mapping.png)

The foundation every tool builds on. Upload any pipeline CSV; the app:

1. Auto-suggests a mapping from your headers to the canonical schema (you confirm
   every field — suggestions are never applied silently).
2. Lets you resolve the date format with a live preview (`auto` infers from the
   data; ambiguous dates like `03/04/2026` force an explicit choice rather than
   guessing).
3. Assigns raw sales-stage strings to canonical buckets (`early | mid | late |
   closed_won | closed_lost`); unmapped stages surface for one-click assignment.
4. Validates the frame (unparseable dates, negative amounts, missing required
   fields, duplicate/blank opportunity IDs) — blocking errors vs. warnings.
5. Saves the mapping as a **named profile** so next week's export is a zero-click
   re-import, and stores the rows as an append-only snapshot (keyed by file hash,
   so re-importing the same file is caught).

The canonical schema has six required fields (`account_name`,
`opportunity_name`, `stage`, `amount`, `close_date`, `owner`) and optional fields
that unlock richer analysis when present (`opportunity_id` — the join key for
week-over-week deltas — plus `forecast_category`, `probability`, `product`,
`sub_vertical`, `exec_sponsor`, and date fields).

### 1. Forecast Narrative

![Forecast Narrative — metrics, week-over-week movement, and draft narrative](docs/screenshots/1-forecast-narrative.png)

Drafts the weekly commit / upside / risk story from a snapshot:

- **Bucket rollup** — commit/upside/pipeline totals, using `forecast_category`
  when present and falling back to a stage-derived category otherwise.
- **Week-over-week movement** — row-level matching: rows with an
  `opportunity_id` join on ID (so a renamed deal is *moved*, not
  new+disappeared); ID-less rows join on normalized names; anything left over is
  surfaced as an explicit `unmatched` count rather than silently miscounted.
- **Risk flags** — rule-based and evidence-backed (`config/risk_rules.yaml`):
  `stalled` (stage age past a threshold, measured per opportunity across
  snapshots), `slipped` (close date pushed out), `no_sponsor` (large deal with no
  exec sponsor), and `big_and_late` (large deal closing soon but not late-stage).
  Each flag carries a plain-English evidence string.

The numbers are inserted verbatim; the editable prose stays under your control.
Export by copy or `.md` download.

### 2. QBR Assembler

![QBR Assembler — scorecard and native pipeline-by-stage chart](docs/screenshots/2-qbr-assembler.png)

One click from a snapshot to a five-slide `.pptx` (title, scorecard, pipeline-by-
stage native bar chart, top deals, risks & asks) plus a `.md` appendix. Tables
are row/column-capped and long names truncated so slides never overflow; every
slide carries a `DRAFT` footer. A consistency-guard test parses the commit figure
back out of the built deck and asserts it equals the narrative's — the two views
share `core/forecast`, so they cannot drift.

<details>
<summary>Sample <code>.md</code> appendix (generated from the sample data)</summary>

```markdown
# Energy — West — Business Review (Q3 FY26 Business Review)

## Scorecard
- Commit: $8.8M ▬ flat
- Upside: $6.3M ▲ $80K
- Coverage: 1.3x
- At risk: $4.9M

## Pipeline by stage
- early: 8 deals, $845K (Δ -$4.0M)
- mid: 23 deals, $10.2M (Δ -$1.9M)
- late: 6 deals, $8.2M (Δ $6.2M)

## Risks & asks
- Pipeline SCADA Security ($2.1M): in stage '04 Commit' for 49 days (since 2026-06-23)
- Identity Consolidation ($750K): no exec sponsor on a $750K deal
- TSA Directive Gap Closure ($690K): close date moved 2026-08-20 → 2026-11-20 (+92d)
```
</details>

### 3. Account Plan

![Account Plan — obligation to capability to gap crosswalk with whitespace](docs/screenshots/3-account-plan.png)

Joins an account-facts record (installed products, incumbent tools, regulatory
scope, spend) with that account's open pipeline to produce a plan with:

- An **obligation → capability → gap crosswalk** (`config/obligation_map.yaml`,
  `config/product_map.yaml`): each regulatory obligation in the account's scope is
  marked `landed` (a covering product is installed), `partial` (only a competitor
  tool covers it — a displacement play), or `gap`. Reference frameworks shipped as
  examples include NERC CIP, TSA Security Directives, and IEC 62443.
- A **whitespace estimate** — open pipeline whose product maps to a gap capability,
  summed, plus the list of gap capabilities with no pipeline yet. Products that
  can't be resolved are excluded and reported, never guessed.
- Rule-based **next actions** and export to `.pptx`/`.md`.

<details>
<summary>Sample account plan (generated from the sample data)</summary>

```markdown
# Account plan — Meridian Energy

## Obligation → capability → gap
| Obligation | Capability | Product | Status | Evidence |
|---|---|---|---|---|
| CIP-005-7-R2 | identity | Entra | landed | Entra ID |
| CIP-007-6-R3 | endpoint_protection | Defender for Endpoint | partial | CrowdStrike |
| CIP-007-6-R4 | siem | Sentinel | landed | Microsoft Sentinel |
| CIP-011-3-R1 | data_protection | Purview | gap |  |

## Whitespace
- Open pipeline against gap capabilities: $820K

## Next actions
- Displacement play: displace CrowdStrike with Defender for Endpoint (endpoint_protection)
- New capability play: patch_mgmt (Intune / Azure Update Manager) — no pipeline exists yet
```
</details>

---

## Quickstart

Requires Python 3.11+ (developed on 3.14).

```bash
pip install -r requirements.txt

# Seed the demo database with two weekly snapshots + sample account facts
python sample_data/seed_snapshots.py
```

The three tools (Forecast Narrative, QBR Assembler, Account Plan) run as a local
[FastHTML](https://fastht.ml) app; **Home** (ingest & column mapping) is a
separate Streamlit entry:

```bash
# Build the stylesheet once (and after any UI change), then launch the tools
make css                        # or run tools/tailwindcss.exe directly (see Makefile)
uvicorn web.server:app --host 127.0.0.1   # http://127.0.0.1:8000

# Ingest / column mapping (Home) — Streamlit
streamlit run app/Home.py
```

Then walk the tools in order: **Home** (the sample import is already seeded, or
upload `sample_data/energy_pipeline_sample.csv` yourself) → **Forecast Narrative**
→ **QBR Assembler** → **Account Plan**.

> The tool app is for **single-user local use** and is bound to loopback
> (`127.0.0.1`) above. A Host/Origin guard on state-changing requests ships with
> the separate security-hardening change; nothing is ever sent off the machine.

> The screenshots above show the tools running against the bundled sample data,
> and the `<details>` blocks show real, reproducible export output.

## Sample data

- `sample_data/energy_pipeline_sample.csv` — 40 **fictional** rows (invented
  energy companies and contacts) that deliberately exercise every failure class:
  messy headers, a malformed date, an all-ambiguous date pair, a negative amount,
  blank opportunity IDs, unmapped stages, and one account spelled two ways.
- `sample_data/account_facts_sample.csv` — 5 fictional accounts, including an
  all-gap account and a name-mismatch case.
- `sample_data/seed_snapshots.py` — seeds a prior week (backdated, with deliberate
  mutations so week-over-week logic has something to find) and the current week
  via the same import path the UI uses.

## Configuration

All under `config/`, editable YAML read at call time — no code change needed:

| File | Purpose |
|------|---------|
| `stage_map.yaml` | Raw sales-stage string → canonical bucket |
| `aliases.yaml` | Account/owner name normalization (canonical → aliases) |
| `risk_rules.yaml` | Thresholds for the four risk flags |
| `narrative_templates.yaml` | Sentence templates for the forecast narrative |
| `obligation_map.yaml` | Regulatory obligation → required capability |
| `product_map.yaml` | Product/competitor names → capability category |

## Architecture

```
config/       editable YAML (stage map, aliases, rules, templates, crosswalk)
core/         pure logic, no UI:
                schema, ingest, mapping, store, importer   (foundation)
                forecast, narrative, formatting            (tools 1-2)
                deck, styles                               (tool 2)
                crosswalk, plan                            (tool 3)
                views/                                     (per-tool view models)
web/          FastHTML app for the three tools:
                server (ASGI), routes/, components, static/ (vendored htmx +
                built Tailwind)
app/          Streamlit entry: Home.py (ingest & mapping) + mapping_ui helpers
sample_data/  fictional sample CSVs + seed script
tests/        pytest suite (143 tests)
data/         SQLite database (created at runtime, git-ignored)
```

The `core/` modules are pure functions over stored snapshots with no UI imports,
so all logic is exercised headlessly by the test suite. The three tools render
through a thin FastHTML layer (`web/`) whose view models (`core/views/`) reuse
the same `core/` functions the exports do — the on-screen numbers and the
`.pptx`/`.md` downloads cannot disagree. Ingest & column mapping (Home) remain
a Streamlit entry (`app/`), so the app currently has two UI surfaces over one
shared core.

## Data handling

- **The bundled sample data is entirely fictional.** Every company, contact, and
  deal in `sample_data/` is invented.
- **Real CRM exports never belong in this repo.** `data/` and root-level `*.csv`
  are git-ignored; only the `sample_data/` CSVs are tracked. Any real export and
  the runtime `data/agents.db` stay on the operator's own machine.
- The tools are strictly read-only with respect to external systems: no writes to
  any CRM, no network calls, no telemetry. Exports are local downloads labeled as
  drafts.
- Product and regulatory names that appear in the sample data (e.g. Microsoft
  Sentinel, Entra ID, Splunk, NERC CIP) are public product/standard names used
  only as realistic example values.

## Testing

```bash
python -m pytest
```

143 tests cover the ingest/mapping pipeline, forecast analytics (including
week-over-week matching and risk-flag boundaries), deck consistency, the
compliance crosswalk, the per-tool view models, and the FastHTML routes
(including golden parity gates that hold the `.md`/`.pptx` exports byte- and
content-stable). Tests use throwaway temp databases and never touch
`data/agents.db`.

## Not included (by design)

LLM/AI polish of the draft text, a manager roll-up view, a branded deck template,
multi-user auth, and multi-currency handling are intentionally out of scope for
this version.
