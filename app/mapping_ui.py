"""Upload-independent Streamlit components for the mapping flow.

Each component takes a DataFrame (already loaded via core.ingest.load_csv), so
the flow is testable without driving st.file_uploader, and reusable for other
canonical schemas later.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core import ingest, schema

NOT_MAPPED = "— not mapped —"


def render_mapping_grid(
    df: pd.DataFrame, suggested: dict[str, str | None], key_prefix: str = "map",
    target_schema: schema.Schema | None = None,
) -> dict[str, str | None]:
    """One row per canonical field: description, source-column selectbox
    (pre-selected from suggestions), live sample values. Returns the mapping."""
    sch = target_schema or schema.PIPELINE_SCHEMA
    headers = list(df.columns)
    result: dict[str, str | None] = {}
    for section, fields in (
        ("Required fields", sch.required),
        ("Optional fields", sch.optional),
    ):
        st.subheader(section)
        for field, spec in fields.items():
            col_name, col_pick, col_sample = st.columns([2, 2, 3])
            options = [NOT_MAPPED] + headers
            default = suggested.get(field)
            index = options.index(default) if default in options else 0
            with col_name:
                st.markdown(f"**{field}**")
                st.caption(spec["description"])
            with col_pick:
                choice = st.selectbox(
                    field, options, index=index, key=f"{key_prefix}_{field}",
                    label_visibility="collapsed",
                )
            with col_sample:
                if choice != NOT_MAPPED:
                    samples = [v for v in df[choice].head(8) if str(v).strip()][:3]
                    st.caption("e.g. " + " | ".join(str(s) for s in samples))
            result[field] = None if choice == NOT_MAPPED else choice
    return result


def render_date_format_choice(
    df: pd.DataFrame, mapping: dict[str, str | None], default: str = "auto",
    key_prefix: str = "map", target_schema: schema.Schema | None = None,
) -> str:
    """Date format selector with a live preview of parsed sample dates so a
    misparse is visible before import."""
    labels = {
        "auto": "Auto-detect", "mdy": "US (month/day/year)",
        "dmy": "International (day/month/year)", "iso": "ISO (yyyy-mm-dd)",
    }
    options = list(labels)
    fmt = st.radio(
        "Date format", options, index=options.index(default if default in options else "auto"),
        format_func=labels.get, horizontal=True, key=f"{key_prefix}_datefmt",
    )
    sch = target_schema or schema.PIPELINE_SCHEMA
    date_cols = [mapping[f] for f in sch.date_fields if mapping.get(f)]
    if date_cols:
        sample = df[date_cols[0]].head(20)
        sample = sample[sample.str.strip() != ""].head(3)
        try:
            resolved = fmt
            if fmt == "auto":
                resolved = ingest.infer_date_format(
                    [df[c] for c in date_cols]
                )
            parsed, _ = ingest.parse_date_series(sample, resolved)
            preview = " | ".join(
                f"{raw} → {p or 'unparseable'}" for raw, p in zip(sample, parsed)
            )
            st.caption(f"Preview ({resolved}): {preview}")
        except ingest.AmbiguousDateFormat:
            st.error(
                "Every date in this file is ambiguous (e.g. 03/04/2026) — "
                "auto-detect cannot decide. Choose US or International explicitly."
            )
        except ingest.ConflictingDateFormat as e:
            st.error(str(e))
    return fmt


def render_stage_assignment(
    df: pd.DataFrame, mapping: dict[str, str | None],
    defaults: dict[str, str], key_prefix: str = "map",
) -> dict[str, str]:
    """Bucket selectboxes for each distinct raw stage; unknowns highlighted."""
    buckets = ["", "early", "mid", "late", "closed_won", "closed_lost"]
    stage_col = mapping.get("stage")
    if not stage_col:
        st.info("Map the stage field to assign stage buckets.")
        return {}
    lowered_defaults = {str(k).lower(): v for k, v in defaults.items()}
    raw_stages = sorted({s.strip() for s in df[stage_col] if str(s).strip()})
    assignments: dict[str, str] = {}
    unknown = [s for s in raw_stages if s.lower() not in lowered_defaults]
    if unknown:
        st.warning("Unmapped stage value(s) — assign a bucket: " + ", ".join(unknown))
    cols = st.columns(3)
    for i, raw in enumerate(raw_stages):
        default = lowered_defaults.get(raw.lower(), "")
        with cols[i % 3]:
            choice = st.selectbox(
                raw, buckets, index=buckets.index(default) if default in buckets else 0,
                key=f"{key_prefix}_stage_{raw}",
            )
        if choice:
            assignments[raw] = choice
    return assignments


def render_validation(issues: list[dict]) -> bool:
    """Show blocking errors vs warnings. Returns True if blocked."""
    blocking = [i for i in issues if i["severity"] == schema.BLOCKING]
    warnings = [i for i in issues if i["severity"] == schema.WARNING]
    for i in blocking:
        st.error(i["message"])
    if warnings:
        with st.expander(f"{len(warnings)} warning(s) — rows import as-is", expanded=True):
            for i in warnings:
                st.warning(i["message"])
    if not blocking and not warnings:
        st.success("No validation issues.")
    return bool(blocking)
