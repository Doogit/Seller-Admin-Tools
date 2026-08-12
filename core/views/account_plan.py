"""View model for tool 3 (Account Plan).

Pure: no web/Streamlit imports. Wraps the same read-only core the .md/.pptx
downloads use (crosswalk.gap_table / whitespace_estimate + plan.compose), so the
on-screen plan can't disagree with the exported artifacts. The reactive import
grid is modelled here too as pure data (import_preview) — the route only renders
it; the mapping/date logic lives in core.mapping / core.ingest, mirrored from
app/mapping_ui.py so the two UIs behave identically.

No config writes happen here. Alias-confirm and product-assign are single-action
POSTs owned by the route (core.ingest.append_alias /
crosswalk.append_product_alias); build() stays read-only.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from core import crosswalk, ingest, mapping, plan, schema, store
from core.views import common

# --- verbatim strings (inventory §1b) ---------------------------------------
EMPTY_STATE = ("Import an account-facts CSV to begin. "
               "Sample: sample_data/account_facts_sample.csv")
NO_OBLIGATIONS = ("No obligations in scope — set regulatory_scope in the account "
                  "facts to drive the crosswalk.")
NO_NEAR_NAMES = "No near-name pipeline accounts found."
NO_PIPELINE_SNAPSHOTS = "No pipeline snapshots — plan will render without pipeline."
UNMEASURABLE_WHITESPACE = (
    "No `product` field populated on this account's open pipeline — whitespace "
    "can't be measured (shown as $0, not a true zero). Map the product column on "
    "Home to enable it.")
REQUIRED_NOT_MAPPED = "Required fields not mapped: "
FOOTER = "Draft — review before use. Read-only: nothing is sent anywhere."

# Metric labels (ui.metric strings, ported verbatim).
METRIC_WHITESPACE = "Whitespace (gap-category pipeline)"
METRIC_UNCOVERED = "Uncovered gaps (no play yet)"
METRIC_OBLIGATIONS = "Obligations in scope"

# Obligation status glyphs (page L146).
STATUS_EMOJI = {"landed": "🟢", "partial": "🟡", "gap": "🔴"}

# Mapping-grid / date-format affordances (mirrors app/mapping_ui.py).
NOT_MAPPED = "— not mapped —"
DATE_FORMAT_LABELS = {
    "auto": "Auto-detect", "mdy": "US (month/day/year)",
    "dmy": "International (day/month/year)", "iso": "ISO (yyyy-mm-dd)",
}
AMBIGUOUS_DATE_ERROR = (
    "Every date in this file is ambiguous (e.g. 03/04/2026) — auto-detect cannot "
    "decide. Choose US or International explicitly.")


def zero_match_warning(display: str) -> str:
    return (f"'{display}' matches zero pipeline rows in this snapshot — likely a "
            "name-spelling difference.")


# --- pre-selection state -----------------------------------------------------

def has_facts(db_path=None) -> bool:
    return not store.load_account_facts(db_path=db_path).empty


def account_options(db_path=None) -> list[tuple[str, str]]:
    """(account_name, display) where display = account_name_raw or account_name."""
    facts = store.load_account_facts(db_path=db_path)
    if facts.empty:
        return []
    return [(r["account_name"], r["account_name_raw"] or r["account_name"])
            for _, r in facts.iterrows()]


def snapshot_options(db_path=None) -> list[tuple[int, str]]:
    return common.snapshot_options(db_path=db_path)


def product_assign_categories() -> list[str]:
    return sorted((crosswalk.load_product_map().get("products") or {}).keys())


# --- reactive import grid (pure model of app/mapping_ui.py) ------------------

def suggest_facts_mapping(headers: list[str]) -> dict[str, str | None]:
    return mapping.suggest_mapping(headers, schema.ACCOUNT_SCHEMA)


def _samples(df, col) -> list[str]:
    return [str(v) for v in df[col].head(8) if str(v).strip()][:3]


def import_preview(df, field_mapping: dict[str, str | None],
                   date_format: str = "auto") -> dict:
    """Per-field source-column options + live samples, date-format preview, and
    missing-required — the data behind the reactive upload grid. Pure mirror of
    mapping_ui.render_mapping_grid + render_date_format_choice."""
    headers = list(df.columns)
    options = [NOT_MAPPED] + headers
    sections = []
    for title, fields in (("Required fields", schema.ACCOUNT_SCHEMA.required),
                          ("Optional fields", schema.ACCOUNT_SCHEMA.optional)):
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

    date = _date_preview(df, field_mapping, date_format)
    missing = [f for f in schema.ACCOUNT_SCHEMA.required if not field_mapping.get(f)]
    return {"sections": sections, "date": date, "missing_required": missing}


def _date_preview(df, field_mapping, date_format) -> dict | None:
    date_cols = [field_mapping[f] for f in schema.ACCOUNT_SCHEMA.date_fields
                 if field_mapping.get(f)]
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


# --- plan view ---------------------------------------------------------------

@dataclass(frozen=True)
class AccountPlanView:
    account_display: str
    summary: list[str]
    metrics: dict
    unmeasurable: bool
    gaps: dict
    uncovered: dict
    unresolved: dict
    pipeline: dict
    next_actions: list[str]
    relationship_map: str
    warnings: list[str]
    zero_match: dict | None
    disclaimer: str
    safe_name: str


def safe_name(display: str) -> str:
    return (display or "account").replace(" ", "_").lower()


def _gaps_block(gaps) -> dict:
    if gaps.empty:
        return {"columns": [], "rows": [], "empty_text": NO_OBLIGATIONS}
    display = gaps.copy()
    display["status"] = display["status"].map(lambda s: f"{STATUS_EMOJI[s]} {s}")
    return {"columns": list(display.columns), "rows": common.table_rows(display),
            "empty_text": None}


def _pipeline_block(pipeline_df) -> dict:
    if pipeline_df is None or pipeline_df.empty:
        return {"columns": [], "rows": []}
    return {"columns": list(pipeline_df.columns), "rows": common.table_rows(pipeline_df)}


def _zero_match(display: str, account_name: str, pipeline_df) -> dict:
    candidates = difflib.get_close_matches(
        account_name, pipeline_df["account_name"].dropna().unique().tolist(),
        n=3, cutoff=0.5)
    return {
        "warning": zero_match_warning(display),
        "candidates": candidates,
        "no_candidates_text": None if candidates else NO_NEAR_NAMES,
    }


def _compute(account_name: str, snapshot_id: int | None, db_path=None) -> dict:
    """Shared read-only pass behind build() and export_inputs() — guarantees the
    on-screen plan and the .md/.pptx downloads come from one crosswalk/compose."""
    facts = store.load_account_facts(db_path=db_path)
    account_row = facts.set_index("account_name").loc[account_name].to_dict()
    account_row["account_name"] = account_name
    display = account_row.get("account_name_raw") or account_name

    pipeline_df = store.get_opportunities(snapshot_id, db_path=db_path) if snapshot_id else None
    account_pipeline = None
    zero = None
    if pipeline_df is not None and not pipeline_df.empty:
        account_pipeline = pipeline_df[pipeline_df["account_name"] == account_name]
        if account_pipeline.empty:
            zero = _zero_match(display, account_name, pipeline_df)

    obligation_map = crosswalk.load_obligation_map()
    gaps = crosswalk.gap_table(account_row, obligation_map)
    ws = crosswalk.whitespace_estimate(gaps, account_pipeline)
    sections = plan.compose(account_row, gaps, ws, account_pipeline)
    return {"gaps": gaps, "ws": ws, "sections": sections, "zero": zero,
            "disclaimer": obligation_map.get("disclaimer", "")}


def export_inputs(account_name: str, snapshot_id: int | None,
                  db_path=None) -> tuple[dict, str]:
    """(sections, disclaimer) for the .md/.pptx download routes."""
    c = _compute(account_name, snapshot_id, db_path=db_path)
    return c["sections"], c["disclaimer"]


def build(account_name: str, snapshot_id: int | None, db_path=None) -> AccountPlanView:
    c = _compute(account_name, snapshot_id, db_path=db_path)
    gaps, ws, sections = c["gaps"], c["ws"], c["sections"]
    return AccountPlanView(
        account_display=sections["account_display"],
        summary=sections["summary"],
        metrics={
            "whitespace": f"${ws['whitespace_amount']:,.0f}",
            "uncovered": len(ws["uncovered"]),
            "obligations": len(gaps),
        },
        unmeasurable=bool(ws.get("unmeasurable")),
        gaps=_gaps_block(gaps),
        uncovered={"rows": common.table_rows(ws["uncovered"])},
        unresolved={"products": ws["unresolved_products"],
                    "categories": product_assign_categories()},
        pipeline=_pipeline_block(sections["pipeline"]),
        next_actions=sections["next_actions"],
        relationship_map=sections["relationship_map"],
        warnings=list(gaps.attrs.get("warnings", [])),
        zero_match=c["zero"],
        disclaimer=c["disclaimer"],
        safe_name=safe_name(sections["account_display"]),
    )
