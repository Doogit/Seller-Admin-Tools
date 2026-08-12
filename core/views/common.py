"""View-model helpers shared by more than one tool page — the presentation-layer
analogue of app/ui.py's shared render helpers (metric_row, risk_table,
snapshot_labels). Pure: no web/Streamlit imports. Sharing these guarantees, e.g.,
that the QBR scorecard strings are identical to the Forecast Narrative metrics
for the same snapshot (a stated requirement), not merely coincidentally equal.
"""

from __future__ import annotations

import pandas as pd

from core import store
from core.formatting import fmt_money

# Load-bearing strings shared across tools (ported verbatim).
EMPTY_STATE = "No snapshots yet — import a pipeline CSV on the Home page first."
PRIOR_NONE_LABEL = "— none —"
DERIVED_NOTE = "Buckets derived from stage — map forecast_category for accuracy."
NO_RISK_FLAGS = "No risk flags."
COVERAGE_EMPTY = "—"


# --- snapshot selection ------------------------------------------------------

def option_label(row) -> str:
    return f"{row['label']} (as of {row['as_of_date']}, {row['n_rows']} rows)"


def snapshot_options(db_path=None) -> list[tuple[int, str]]:
    snaps = store.list_snapshots(db_path=db_path)
    if snaps.empty:
        return []
    return [(int(r["id"]), option_label(r)) for _, r in snaps.iterrows()]


def default_selection(options: list[tuple[int, str]]) -> tuple[int | None, int | None]:
    """current = most recent (index 0); prior = next most recent, or None."""
    if not options:
        return None, None
    return options[0][0], (options[1][0] if len(options) > 1 else None)


# --- table cells -------------------------------------------------------------

def money_cell(x) -> str:
    return fmt_money(x) if pd.notna(x) else ""


def table_rows(df: pd.DataFrame) -> list[dict]:
    """Records with the amount column money-formatted and NaN -> "" (tables are
    out of byte-parity scope; values still trace to core)."""
    out = []
    for rec in df.to_dict("records"):
        row = {k: ("" if pd.isna(v) else v) for k, v in rec.items()}
        if "amount" in rec:
            row["amount"] = money_cell(rec["amount"])
        out.append(row)
    return out


# --- metric scorecard (ui.metric_row) ----------------------------------------

def metric_block(rollup: dict, prior_rollup: dict | None, quota: float | None,
                 at_risk: float) -> dict:
    return {
        "commit": fmt_money(rollup["commit"]),
        "upside": fmt_money(rollup["upside"]),
        "at_risk": fmt_money(at_risk),
        "coverage": (f"{rollup['total_open'] / quota:.1f}x" if quota
                     else COVERAGE_EMPTY),
        "commit_delta": (fmt_money(rollup["commit"] - prior_rollup["commit"])
                         if prior_rollup else None),
        "upside_delta": (fmt_money(rollup["upside"] - prior_rollup["upside"])
                         if prior_rollup else None),
        "derived_note": DERIVED_NOTE if rollup.get("derived") else None,
        "unclassified_note": (
            f"{fmt_money(rollup['unclassified'])} open in unmapped stages is "
            "excluded from coverage." if rollup.get("unclassified_count") else None),
    }


# --- risk table (ui.risk_table) ----------------------------------------------

def risk_block(flags: pd.DataFrame) -> dict:
    notes = [f"Note: {n}" for n in (flags.attrs.get("notes", []) if flags is not None else [])]
    if flags is None or flags.empty:
        return {"notes": notes, "columns": [], "rows": [], "empty_text": NO_RISK_FLAGS}
    table = flags.drop(columns=["opportunity_id"], errors="ignore")
    return {"notes": notes, "columns": list(table.columns),
            "rows": table_rows(table), "empty_text": None}
