"""Home: upload a pipeline CSV → map columns → confirm → save snapshot."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for p in (str(REPO_ROOT), str(REPO_ROOT / "app")):
    if p not in sys.path:
        sys.path.insert(0, p)

import streamlit as st
import yaml

import mapping_ui
from core import importer, ingest, mapping, schema

st.set_page_config(page_title="Sales Admin Agents", layout="wide")
st.title("Pipeline import & column mapping")
st.caption(
    "Read-only, local-only. Nothing is sent anywhere; data stays in data/agents.db."
)

STAGE_MAP_DEFAULTS = yaml.safe_load(
    (REPO_ROOT / "config" / "stage_map.yaml").read_text(encoding="utf-8")
)["stages"]
ALIAS_INDEX = ingest.load_alias_index(REPO_ROOT / "config" / "aliases.yaml")

# 1. Upload + profile
uploaded = st.file_uploader("Pipeline CSV export", type=["csv"])
profiles = mapping.load_profiles()
profile_name = st.selectbox("Mapping profile", ["New mapping"] + sorted(profiles))
profile = profiles.get(profile_name)

if uploaded is None:
    st.info("Upload a pipeline CSV to begin. Sample: sample_data/energy_pipeline_sample.csv")
    st.stop()

raw_bytes = uploaded.getvalue()
try:
    df = ingest.load_csv(raw_bytes)
except ingest.IngestError as e:
    st.error(str(e))
    st.stop()

# 2. Detected headers + preview
st.subheader("Detected columns")
st.caption(", ".join(df.columns))
st.dataframe(df.head(5), width="stretch")

# 3. Mapping grid
suggested = profile["mapping"] if profile else mapping.suggest_mapping(list(df.columns))
field_mapping = mapping_ui.render_mapping_grid(df, suggested)
missing_required = [f for f in schema.REQUIRED_FIELDS if not field_mapping.get(f)]

# 4. Date format
st.subheader("Date format")
date_format = mapping_ui.render_date_format_choice(
    df, field_mapping, default=profile["date_format"] if profile else "auto"
)

# 5. Stage assignment
st.subheader("Stage buckets")
stage_defaults = dict(STAGE_MAP_DEFAULTS)
if profile:
    stage_defaults.update(profile["stage_assignments"])
stage_assignments = mapping_ui.render_stage_assignment(df, field_mapping, stage_defaults)

# 6. Validation
st.subheader("Validation")
blocked = bool(missing_required)
if missing_required:
    st.error("Required fields not mapped: " + ", ".join(missing_required))
else:
    try:
        canonical, problems, _ = ingest.apply_mapping(
            df, field_mapping, date_format, alias_index=ALIAS_INDEX
        )
        issues = schema.validate_frame(canonical)
        issues.extend({"severity": schema.WARNING, "message": p} for p in problems)
        blocked = mapping_ui.render_validation(issues)
    except (ingest.AmbiguousDateFormat, ingest.ConflictingDateFormat) as e:
        st.error(str(e))
        blocked = True

# 7. Confirm & save
st.subheader("Confirm import")
col1, col2, col3 = st.columns(3)
with col1:
    save_as = st.text_input("Save profile as", value=profile_name if profile else "")
with col2:
    default_label = f"wk{dt.date.today().isocalendar().week}"
    label = st.text_input("Snapshot label", value=default_label)
with col3:
    as_of = st.date_input("Data as-of date", value=dt.date.today())

override = st.session_state.get("dup_override", False)
if st.button("Confirm import", type="primary", disabled=blocked or not label):
    profile_id = None
    name = save_as.strip()
    if name.lower() == "new mapping":
        st.warning("'New mapping' is a reserved name — profile not saved.")
    elif name:
        existing = profiles.get(name)
        merged_stages = dict(stage_assignments)
        if existing:
            # keep assignments for stages absent from this file
            merged_stages = {**existing["stage_assignments"], **stage_assignments}
        profile_id = mapping.save_profile(name, field_mapping, merged_stages, date_format)
    result = importer.import_snapshot(
        raw_bytes, field_mapping, date_format, stage_assignments, label,
        as_of_date=as_of, on_duplicate="override" if override else "ask",
        profile_id=profile_id, alias_index=ALIAS_INDEX,
    )
    if result.skipped:
        st.session_state["pending_duplicate"] = result.duplicate_of
    else:
        st.session_state.pop("pending_duplicate", None)
        st.session_state.pop("dup_override", None)
        st.success(
            f"Imported snapshot '{label}': {result.n_rows} rows, "
            f"{result.n_accounts} accounts, ${result.total_amount:,.0f} total pipeline."
        )
        for w in result.warnings:
            st.warning(w)

# Rendered outside the button branch so the checkbox survives the rerun its
# own tick triggers — inside the branch Streamlit would drop the widget.
if st.session_state.get("pending_duplicate"):
    dup = st.session_state["pending_duplicate"]
    st.warning(
        f"Already imported as '{dup['label']}' on {dup['imported_at']}. "
        "Tick the box and press Confirm import again to import anyway."
    )
    st.checkbox("Import anyway (creates a duplicate snapshot)", key="dup_override")
