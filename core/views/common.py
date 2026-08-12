"""View-model helpers shared by more than one tool page — the presentation-layer
analogue of app/ui.py's shared render helpers (metric_row, risk_table,
snapshot_labels). Pure: no web/Streamlit imports. Sharing these guarantees, e.g.,
that the QBR scorecard strings are identical to the Forecast Narrative metrics
for the same snapshot (a stated requirement), not merely coincidentally equal.
"""

from __future__ import annotations

import pandas as pd

from core import ingest, schema, store
from core.formatting import fmt_money

# Load-bearing strings shared across tools (ported verbatim).
EMPTY_STATE = "No snapshots yet — import a pipeline CSV on the Home page first."
PRIOR_NONE_LABEL = "— none —"
DERIVED_NOTE = "Buckets derived from stage — map forecast_category for accuracy."
NO_RISK_FLAGS = "No risk flags."
COVERAGE_EMPTY = "—"

# Reactive import-grid affordances — shared by Home (PIPELINE_SCHEMA) and Account
# Plan (ACCOUNT_SCHEMA). Pure mirror of app/mapping_ui.render_mapping_grid +
# render_date_format_choice; the route only renders the returned data.
NOT_MAPPED = "— not mapped —"
DATE_FORMAT_LABELS = {
    "auto": "Auto-detect", "mdy": "US (month/day/year)",
    "dmy": "International (day/month/year)", "iso": "ISO (yyyy-mm-dd)",
}
AMBIGUOUS_DATE_ERROR = (
    "Every date in this file is ambiguous (e.g. 03/04/2026) — auto-detect cannot "
    "decide. Choose US or International explicitly.")
REQUIRED_NOT_MAPPED = "Required fields not mapped: "


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


# --- reactive import grid (pure model of app/mapping_ui.py) ------------------

def _samples(df, col) -> list[str]:
    return [str(v) for v in df[col].head(8) if str(v).strip()][:3]


def import_preview(df, field_mapping: dict[str, str | None],
                   sch: schema.Schema, date_format: str = "auto") -> dict:
    """Per-field source-column options + live samples, date-format preview, and
    missing-required — the data behind the reactive upload grid, for any schema.
    Pure mirror of mapping_ui.render_mapping_grid + render_date_format_choice."""
    headers = list(df.columns)
    options = [NOT_MAPPED] + headers
    sections = []
    for title, fields in (("Required fields", sch.required),
                          ("Optional fields", sch.optional)):
        rows = []
        for field, spec in fields.items():
            col = field_mapping.get(field)
            rows.append({
                "field": field,
                "description": spec["description"],
                "options": options,
                "selected": col if col in headers else NOT_MAPPED,
                "samples": _samples(df, col) if col in headers else [],
            })
        sections.append({"title": title, "fields": rows})

    date = _date_preview(df, field_mapping, sch, date_format)
    missing = [f for f in sch.required if not field_mapping.get(f)]
    return {"sections": sections, "date": date, "missing_required": missing}


def _date_preview(df, field_mapping, sch: schema.Schema, date_format) -> dict | None:
    date_cols = [field_mapping[f] for f in sch.date_fields if field_mapping.get(f)]
    if not date_cols:
        return None
    out = {"date_format": date_format, "resolved": None, "rows": [], "error": None}
    sample = df[date_cols[0]].head(20)
    sample = sample[sample.str.strip() != ""].head(3)
    try:
        resolved = date_format
        if date_format == "auto":
            resolved = ingest.infer_date_format([df[c] for c in date_cols])
        parsed, _ = ingest.parse_date_series(sample, resolved)
        out["resolved"] = resolved
        out["rows"] = [{"raw": raw, "parsed": p or "unparseable"}
                       for raw, p in zip(sample, parsed)]
    except ingest.AmbiguousDateFormat:
        out["error"] = AMBIGUOUS_DATE_ERROR
    except ingest.ConflictingDateFormat as e:
        out["error"] = str(e)
    return out


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
    # 'action' is the suggested coaching ask (risk_rules.yaml) — relabel it for
    # display, matching app/ui.py's column_config("action" -> "suggested ask").
    table = (flags.drop(columns=["opportunity_id"], errors="ignore")
             .rename(columns={"action": "suggested ask"}))
    return {"notes": notes, "columns": list(table.columns),
            "rows": table_rows(table), "empty_text": None}
