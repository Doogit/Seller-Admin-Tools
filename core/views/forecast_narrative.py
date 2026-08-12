"""View model for tool 1 (Forecast Narrative).

Pure functions over core (forecast, narrative, store) — NO web/Streamlit imports.
Every user-facing string and all formatting that app/ui.py + the page body
produced lives here once, so the FastHTML route renders values verbatim and the
parity gate sees everything. Traceability: docs/migration/forecast_narrative-inventory.md.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from core import forecast, narrative, store
from core.formatting import fmt_money

# --- Static, load-bearing strings (ported verbatim — inventory §1b / §C). ---
EMPTY_STATE = "No snapshots yet — import a pipeline CSV on the Home page first."
PRIOR_NONE_LABEL = "— none —"
DERIVED_NOTE = "Buckets derived from stage — map forecast_category for accuracy."
NO_RISK_FLAGS = "No risk flags."
COVERAGE_EMPTY = "—"
FOOTER = "Draft — review before submitting. Read-only: nothing is sent anywhere."
# 🟢/🟡/🔴 carry meaning via the adjacent word, not colour alone (a11y).
SECTION_LABELS = {"commit": "🟢 Commit", "upside": "🟡 Upside", "risk": "🔴 Risk"}
SECTIONS = ("commit", "upside", "risk")


@dataclass(frozen=True)
class ForecastView:
    snapshot_options: list[tuple[int, str]]
    prior_options: list[tuple[int, str]]
    current_id: int
    prior_id: int | None
    quota: float | None
    metrics: dict
    unmatched: dict
    draft: dict
    risk: dict
    movement: dict
    period: str


# --- helpers -----------------------------------------------------------------

def _option_label(row) -> str:
    return f"{row['label']} (as of {row['as_of_date']}, {row['n_rows']} rows)"


def _money_cell(x) -> str:
    return fmt_money(x) if pd.notna(x) else ""


def _rows(df: pd.DataFrame) -> list[dict]:
    """Table rows with the amount column money-formatted (tables are out of the
    byte-parity golden scope; values still trace to core)."""
    out = []
    for rec in df.to_dict("records"):
        row = {k: ("" if pd.isna(v) else v) for k, v in rec.items()}
        if "amount" in rec:
            row["amount"] = _money_cell(rec["amount"])
        out.append(row)
    return out


def _metrics(rollup: dict, prior_rollup: dict | None, quota: float | None,
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


def _unmatched(deltas: pd.DataFrame | None) -> dict:
    if deltas is None:
        return {"n": 0, "warning": None}
    n = int((deltas["change_type"] == "unmatched").sum())
    warning = (f"{n} opportunities couldn't be matched to last week — "
               "renamed or ID missing? See the movement table.") if n else None
    return {"n": n, "warning": warning}


def _risk(flags: pd.DataFrame) -> dict:
    notes = [f"Note: {note}" for note in (flags.attrs.get("notes", []) if flags is not None else [])]
    if flags is None or flags.empty:
        return {"notes": notes, "columns": [], "rows": [], "empty_text": NO_RISK_FLAGS}
    table = flags.drop(columns=["opportunity_id"], errors="ignore")
    return {"notes": notes, "columns": list(table.columns),
            "rows": _rows(table), "empty_text": None}


def _movement(deltas: pd.DataFrame | None) -> dict:
    if deltas is None or deltas.empty:
        return {"columns": [], "rows": []}
    return {"columns": list(deltas.columns), "rows": _rows(deltas)}


# --- public API --------------------------------------------------------------

def snapshot_options(db_path=None) -> list[tuple[int, str]]:
    snaps = store.list_snapshots(db_path=db_path)
    if snaps.empty:
        return []
    return [(int(r["id"]), _option_label(r)) for _, r in snaps.iterrows()]


def default_selection(options: list[tuple[int, str]]) -> tuple[int | None, int | None]:
    """Mirror the Streamlit page defaults: current = most recent (index 0),
    prior = the next most recent, or None when only one snapshot exists."""
    if not options:
        return None, None
    current = options[0][0]
    prior = options[1][0] if len(options) > 1 else None
    return current, prior


def period_for(current_id: int, db_path=None) -> str:
    """Period label = first token of the snapshot's option label, matching the
    page transform `labels[current_id].split(" ")[0]` (inventory §C-12)."""
    for sid, label in snapshot_options(db_path=db_path):
        if sid == current_id:
            return label.split(" ")[0]
    return ""


def _core_slice(current_id: int, prior_id: int | None, db_path=None):
    rollup = forecast.bucket_rollup(current_id, db_path=db_path)
    prior_rollup = (forecast.bucket_rollup(prior_id, db_path=db_path)
                    if prior_id else None)
    deltas = forecast.wow_delta(current_id, prior_id, db_path=db_path)
    flags = forecast.risk_flags(current_id, db_path=db_path)
    return rollup, prior_rollup, deltas, flags


def draft_sections(current_id: int, prior_id: int | None, quota: float | None,
                   db_path=None) -> dict:
    """The three narrative strings for the given selection — generated by core
    (never restated here). Used to (re)generate the draft region."""
    rollup, prior_rollup, deltas, flags = _core_slice(current_id, prior_id, db_path=db_path)
    return narrative.draft(rollup, deltas, flags, prior_rollup=prior_rollup,
                           quota=quota or None)


def metrics_view(current_id: int, prior_id: int | None, quota: float | None,
                 db_path=None) -> dict:
    """Metrics/coverage panel only — for the quota-scoped partial swap that must
    leave the draft textarea untouched (inventory §C, quota preserves edits)."""
    rollup, prior_rollup, deltas, flags = _core_slice(current_id, prior_id, db_path=db_path)
    return _metrics(rollup, prior_rollup, quota, forecast.at_risk_total(flags))


def export_markdown(sections: dict, period: str) -> str:
    """Assemble the .md export from (possibly edited) sections — thin passthrough
    so the route need not import core.narrative directly."""
    return narrative.assemble_markdown(sections, period=period)


def build(current_id: int, prior_id: int | None, quota: float | None,
          db_path=None) -> ForecastView:
    options = snapshot_options(db_path=db_path)
    prior_options = [o for o in options if o[0] != current_id]
    rollup, prior_rollup, deltas, flags = _core_slice(current_id, prior_id, db_path=db_path)
    sections = narrative.draft(rollup, deltas, flags, prior_rollup=prior_rollup,
                               quota=quota or None)
    return ForecastView(
        snapshot_options=options,
        prior_options=prior_options,
        current_id=current_id,
        prior_id=prior_id,
        quota=quota,
        metrics=_metrics(rollup, prior_rollup, quota, forecast.at_risk_total(flags)),
        unmatched=_unmatched(deltas),
        draft=sections,
        risk=_risk(flags),
        movement=_movement(deltas),
        period=period_for(current_id, db_path=db_path),
    )
