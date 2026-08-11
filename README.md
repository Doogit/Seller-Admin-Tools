# sales-admin-agents

Local, read-only admin tools for enterprise sellers: CSV pipeline ingest with a
reusable column-mapping layer, weekly forecast narrative drafting, QBR deck
assembly, and account plan generation. Single operator, no auth, no network
calls — everything stays on this machine (SQLite file + session state).

## Quickstart

```
pip install -r requirements.txt
streamlit run app/Home.py
```

1. **Home** — upload any pipeline CSV export, map its columns to the canonical
   schema (suggestions are pre-filled; you confirm everything), assign stage
   buckets, and save the import as a snapshot. Mappings persist as named
   profiles so the next weekly export is a zero-click re-import.
2. **Pages 1–3** (added by later sessions) — forecast narrative, QBR assembler,
   account plan generator, all reading from the saved snapshots.

Sample data: `sample_data/energy_pipeline_sample.csv` (40 fictional rows,
deliberately messy). Seed demo snapshots with
`python sample_data/seed_snapshots.py`.

Tests: `python -m pytest`

## Data handling

- **Pre-hire: fictional data only.** Everything in `sample_data/` is invented.
- **Post-hire: real CRM exports and `data/agents.db` exist ONLY on a
  corporate-managed device.** Never commit real exports: `data/` and root-level
  `*.csv` are git-ignored (only `sample_data/` CSVs are tracked).
- The tools are read-only: no writes to any external system, no network calls,
  no telemetry. Exports are local file downloads labeled as drafts.
- Vendor-neutral: no CRM-specific column names in core logic. Stage labels and
  name aliases live in `config/`, not code.

## Repo layout

```
config/       stage_map.yaml, aliases.yaml (+ tool configs in later sessions)
core/         schema, ingest, mapping, store, importer — pure logic, no UI
app/          Streamlit entry (Home.py) + pages/
sample_data/  fictional sample CSV + seed script
tests/        pytest suite
data/         SQLite database (created at runtime, git-ignored)
```
