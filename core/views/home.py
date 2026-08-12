"""View model for Home — the pipeline-import wizard (upload → column mapping →
date format → stage-bucket assignment → validation → confirm import).

Pure: no web/Streamlit imports. Mirrors app/Home.py + app/mapping_ui.py so the
FastHTML and Streamlit ingest flows behave identically. The reactive mapping
grid + date preview are modelled by core.views.common.import_preview (shared
with Account Plan); this module adds the stage-bucket and validation blocks and
the confirm-import affordances. All user-facing strings live here once; the
route renders them verbatim.

No db/config writes happen here — build_grid() is read-only. The snapshot write
(importer.import_snapshot) and profile save (mapping.save_profile) are owned by
the route, behind the loopback + CSRF middleware.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import yaml

from core import ingest, mapping, schema
from core.views import common

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# --- verbatim strings (inventory §1b) ---------------------------------------
CAPTION = ("Read-only, local-only. Nothing is sent anywhere; data stays in "
           "data/agents.db.")
UPLOAD_HINT = ("Upload a pipeline CSV to begin. "
               "Sample: sample_data/energy_pipeline_sample.csv")
STAGE_NEEDS_MAPPING = "Map the stage field to assign stage buckets."
STAGE_UNMAPPED_PREFIX = "Unmapped stage value(s) — assign a bucket: "
NO_VALIDATION_ISSUES = "No validation issues."
RESERVED_NAME_WARNING = "'New mapping' is a reserved name — profile not saved."
FOOTER = "Read-only: nothing is sent anywhere."

# Selectors / affordances shared with the account-facts grid.
NOT_MAPPED = common.NOT_MAPPED
DATE_FORMAT_LABELS = common.DATE_FORMAT_LABELS
REQUIRED_NOT_MAPPED = common.REQUIRED_NOT_MAPPED

NEW_MAPPING = "New mapping"                       # reserved "no profile" option
STAGE_BUCKETS = ["", "early", "mid", "late", "closed_won", "closed_lost"]


def duplicate_warning(dup: dict) -> str:
    return (f"Already imported as '{dup['label']}' on {dup['imported_at']}. "
            "Tick the box and press Import anyway to import again.")


def import_success(label: str, n_rows: int, n_accounts: int,
                   total_amount: float) -> str:
    return (f"Imported snapshot '{label}': {n_rows} rows, {n_accounts} accounts, "
            f"${total_amount:,.0f} total pipeline.")


# --- config-backed defaults --------------------------------------------------

def stage_map_defaults() -> dict[str, str]:
    """Raw-stage → bucket defaults from config/stage_map.yaml."""
    return yaml.safe_load(
        (REPO_ROOT / "config" / "stage_map.yaml").read_text(encoding="utf-8"))["stages"]


def alias_index() -> dict[str, str]:
    return ingest.load_alias_index(REPO_ROOT / "config" / "aliases.yaml")


def profile_options(db_path=None) -> list[str]:
    """["New mapping"] + saved profile names (sorted)."""
    return [NEW_MAPPING] + sorted(mapping.load_profiles(db_path=db_path))


def suggest_pipeline_mapping(headers: list[str]) -> dict[str, str | None]:
    return mapping.suggest_mapping(headers)


def default_label(today: dt.date) -> str:
    return f"wk{today.isocalendar().week}"


# --- stage-bucket block ------------------------------------------------------

def stage_preview(df, field_mapping: dict[str, str | None],
                  defaults: dict[str, str], chosen: dict[str, str]) -> dict | None:
    """Bucket assignment for each distinct raw stage value in the mapped stage
    column. `defaults` = stage_map ∪ profile assignments; `chosen` = the user's
    current form selections (take precedence). None → stage field not mapped."""
    stage_col = field_mapping.get("stage")
    if not stage_col:
        return None
    lowered = {str(k).lower(): v for k, v in defaults.items()}
    raw_stages = sorted({s.strip() for s in df[stage_col] if str(s).strip()})
    rows = []
    for raw in raw_stages:
        if raw in chosen:
            bucket = chosen[raw]
        else:
            bucket = lowered.get(raw.lower(), "")
        rows.append({"raw": raw, "bucket": bucket if bucket in STAGE_BUCKETS else ""})
    unknown = [s for s in raw_stages if s.lower() not in lowered]
    return {"rows": rows, "unknown": unknown, "buckets": STAGE_BUCKETS}


def stage_assignments_from(rows: list[dict]) -> dict[str, str]:
    """Collapse stage_preview rows to the {raw: bucket} map importer expects
    (blank buckets dropped, matching render_stage_assignment)."""
    return {r["raw"]: r["bucket"] for r in rows if r["bucket"]}


# --- validation block --------------------------------------------------------

def validate(df, field_mapping: dict[str, str | None], date_format: str,
             alias_idx: dict[str, str] | None) -> dict:
    """Blocking vs warning issues for the current mapping (mirrors Home.py §6).

    Returns {blocking, warnings, error, blocked}. `error` holds an
    ambiguous/conflicting date-format message (also blocking)."""
    missing = [f for f in schema.PIPELINE_SCHEMA.required if not field_mapping.get(f)]
    if missing:
        return {"blocking": [REQUIRED_NOT_MAPPED + ", ".join(missing)],
                "warnings": [], "error": None, "blocked": True}
    try:
        canonical, problems, _ = ingest.apply_mapping(
            df, field_mapping, date_format, alias_index=alias_idx)
    except (ingest.AmbiguousDateFormat, ingest.ConflictingDateFormat) as e:
        return {"blocking": [], "warnings": [], "error": str(e), "blocked": True}
    issues = schema.validate_frame(canonical)
    issues.extend({"severity": schema.WARNING, "message": p} for p in problems)
    blocking = [i["message"] for i in issues if i["severity"] == schema.BLOCKING]
    warnings = [i["message"] for i in issues if i["severity"] == schema.WARNING]
    return {"blocking": blocking, "warnings": warnings, "error": None,
            "blocked": bool(blocking)}


# --- combined grid model -----------------------------------------------------

def build_grid(df, field_mapping: dict[str, str | None], date_format: str,
               chosen_stages: dict[str, str], stage_defaults: dict[str, str],
               alias_idx: dict[str, str] | None) -> dict:
    """The whole reactive region: mapping preview + stage block + validation,
    plus the single `blocked` flag the Confirm button is disabled on. One call
    so the route (and its test) exercise the same unit the UI renders."""
    preview = common.import_preview(df, field_mapping, schema.PIPELINE_SCHEMA, date_format)
    stage = stage_preview(df, field_mapping, stage_defaults, chosen_stages)
    validation = validate(df, field_mapping, date_format, alias_idx)
    blocked = bool(preview["missing_required"]) or validation["blocked"]
    return {"preview": preview, "stage": stage, "validation": validation,
            "blocked": blocked}
