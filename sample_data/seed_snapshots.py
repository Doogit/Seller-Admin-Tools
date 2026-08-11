"""Seed the demo database with two snapshots of the sample pipeline.

Creates (via core.importer — the exact path Home.py uses):
  1. "wk25" — a synthetic PRIOR week, as-of 49 days ago, derived from the
     sample CSV with documented mutations (below).
  2. "wk32" — the sample CSV as-is, as-of today.

Prior-week mutations (all deliberate, to exercise week-over-week logic):
  - Most opportunities are set one MCEM stage earlier, so they appear to have
    advanced into their current stage this period (stage age ~0 days).
  - OP-1005 and OP-1024 keep their current stage -> 49 days in-stage, so the
    "stalled" rule (>=45 days) fires on them in the current snapshot.
  - OP-1018 close date was 8/20/2026, now 11/20/2026 -> "slipped" (>=1 quarter).
  - OP-1021 was named "SIEM Consolidation" -> renamed; must match via
    opportunity_id, not appear as new+disappeared.
  - OP-1011 amount was $480,000 -> amount change.
  - OP-1099 "Legacy AV Renewal" exists only in the prior week -> disappeared.
  - OP-1037, OP-1026, and the blank-ID "Emergency Ops Identity" row exist only
    in the current week -> new (the blank-ID one via name matching).

Run: python sample_data/seed_snapshots.py
"""

from __future__ import annotations

import datetime as dt
import io
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import yaml

from core import importer, ingest, mapping

SAMPLE = REPO_ROOT / "sample_data" / "energy_pipeline_sample.csv"

PRIOR_STAGE = {"04 Achieve": "03 Empower", "03 Empower": "02 Design", "02 Design": "01 Inspire"}
KEEP_STAGE_IDS = {"OP-1005", "OP-1024"}  # stalled candidates
DROP_FROM_PRIOR = {"OP-1037", "OP-1026"}
DROP_NAMES_FROM_PRIOR = {"Emergency Ops Identity"}

PRIOR_ONLY_ROW = {
    "Account": "Delta Refining", "Opportunity": "Legacy AV Renewal",
    "Opportunity ID": "OP-1099", "Sales Stage": "02 Design",
    "Est. Revenue": "$60,000.00", "Close Dt": "9/15/2026",
    "Opportunity Owner": "Marcus Webb", "Forecast Category": "Pipeline",
    "Probability (%)": "25", "Last Activity": "6/1/2026",
    "Sub-Vertical": "Oil & Gas", "Product": "Defender for Endpoint",
    "Exec Sponsor": "", "Created On": "3/1/2026",
}


def build_prior_csv_bytes() -> bytes:
    df = ingest.load_csv(SAMPLE)
    keep = ~(
        df["Opportunity ID"].isin(DROP_FROM_PRIOR)
        | df["Opportunity"].isin(DROP_NAMES_FROM_PRIOR)
    )
    df = df[keep].copy()
    moved = ~df["Opportunity ID"].isin(KEEP_STAGE_IDS)
    df.loc[moved, "Sales Stage"] = df.loc[moved, "Sales Stage"].map(
        lambda s: PRIOR_STAGE.get(s, s)
    )
    df.loc[df["Opportunity ID"] == "OP-1018", "Close Dt"] = "8/20/2026"
    df.loc[df["Opportunity ID"] == "OP-1021", "Opportunity"] = "SIEM Consolidation"
    df.loc[df["Opportunity ID"] == "OP-1011", "Est. Revenue"] = "$480,000.00"
    df = pd.concat([df, pd.DataFrame([PRIOR_ONLY_ROW])], ignore_index=True)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def main() -> None:
    headers = list(ingest.load_csv(SAMPLE).columns)
    field_mapping = mapping.suggest_mapping(headers)
    stage_map = yaml.safe_load(
        (REPO_ROOT / "config" / "stage_map.yaml").read_text(encoding="utf-8")
    )["stages"]
    alias_index = ingest.load_alias_index(REPO_ROOT / "config" / "aliases.yaml")
    profile_id = mapping.save_profile("Energy sample", field_mapping, stage_map, "mdy")

    today = dt.date.today()
    for label, file, as_of in (
        ("wk25", build_prior_csv_bytes(), today - dt.timedelta(days=49)),
        ("wk32", SAMPLE, today),
    ):
        result = importer.import_snapshot(
            file, field_mapping, "mdy", stage_map, label,
            as_of_date=as_of, on_duplicate="skip",
            profile_id=profile_id, alias_index=alias_index,
        )
        if result.blocking:
            print(f"{label}: BLOCKED — {'; '.join(result.blocking)}")
        elif result.skipped:
            print(f"{label}: already imported (skipped)")
        else:
            print(
                f"{label}: snapshot {result.snapshot_id} — {result.n_rows} rows, "
                f"{result.n_accounts} accounts, ${result.total_amount:,.0f} pipeline, "
                f"{len(result.warnings)} warning(s)"
            )
            for w in result.warnings:
                print(f"  - {w}")


if __name__ == "__main__":
    main()
