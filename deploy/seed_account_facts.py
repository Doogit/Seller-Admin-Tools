"""Seed the demo database with the committed sample account facts.

The repo's sample_data/seed_snapshots.py seeds pipeline snapshots (Forecast
Narrative + QBR Assembler); this adds the account facts the Account Plan page
uses, so a demo deployment shows all three tools populated. Uses the same
suggest-mapping + import path the Account Plan page uses when a user uploads.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE = REPO_ROOT / "sample_data" / "account_facts_sample.csv"

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
