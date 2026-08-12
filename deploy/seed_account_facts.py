"""Seed the demo database with the committed sample account facts.

The repo's sample_data/seed_snapshots.py seeds pipeline snapshots (Forecast
Narrative + QBR Assembler); this adds the account facts the Account Plan page
uses, so a demo deployment shows all three tools populated. Uses the same
suggest-mapping + import path the Account Plan page uses when a user uploads.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE = REPO_ROOT / "sample_data" / "account_facts_sample.csv"

# Make `core` importable when run as a script (sys.path[0] is deploy/, not the
# repo root), exactly as sample_data/seed_snapshots.py does.
sys.path.insert(0, str(REPO_ROOT))

from core import importer, ingest, mapping, schema


def main() -> None:
    raw = SAMPLE.read_bytes()
    df = ingest.load_csv(raw)
    suggested = mapping.suggest_mapping(list(df.columns), schema.ACCOUNT_SCHEMA)
    result = importer.import_account_facts(raw, suggested)
    if result.blocking:
        raise SystemExit(f"account-facts seed blocked: {result.blocking}")
    print(f"account facts seeded: {result.n_accounts} accounts")


if __name__ == "__main__":
    main()
