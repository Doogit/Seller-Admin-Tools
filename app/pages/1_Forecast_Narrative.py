"""Tool 1: weekly commit / upside / risk narrative draft."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
for p in (str(REPO_ROOT), str(REPO_ROOT / "app")):
    if p not in sys.path:
        sys.path.insert(0, p)

import streamlit as st

import ui
from core import forecast, narrative, store

st.set_page_config(page_title="Forecast Narrative", layout="wide")
st.title("Forecast narrative")

snaps = store.list_snapshots()
if snaps.empty:
    st.info("No snapshots yet — import a pipeline CSV on the Home page first.")
    st.stop()

labels = ui.snapshot_labels(snaps)
ids = list(labels)

col1, col2, col3 = st.columns(3)
with col1:
    current_id = st.selectbox("Snapshot", ids, index=0, format_func=labels.get)
prior_options = [i for i in ids if i != current_id]
with col2:
    prior_id = st.selectbox(
        "Compare against", [None] + prior_options,
        index=1 if prior_options else 0,
        format_func=lambda i: "— none —" if i is None else labels[i],
    )
with col3:
    quota = st.number_input(
        "Quota (optional, session-only)", min_value=0.0, value=0.0, step=100000.0,
        format="%.0f",
    )

rollup = forecast.bucket_rollup(current_id)
prior_rollup = forecast.bucket_rollup(prior_id) if prior_id else None
deltas = forecast.wow_delta(current_id, prior_id)
flags = forecast.risk_flags(current_id)

ui.metric_row(rollup, prior_rollup, quota or None, forecast.at_risk_total(flags))
ui.unmatched_warning(deltas)

# Drafts — regenerate only on explicit confirm so edits survive reruns
sections = narrative.draft(rollup, deltas, flags, prior_rollup=prior_rollup,
                           quota=quota or None)
draft_key = f"draft_{current_id}_{prior_id}"
if draft_key not in st.session_state:
    st.session_state[draft_key] = sections

st.subheader("Draft — review before submitting")
edited = {}
colors = {"commit": "🟢", "upside": "🟡", "risk": "🔴"}
for section in ("commit", "upside", "risk"):
    edited[section] = st.text_area(
        f"{colors[section]} {section.title()}",
        value=st.session_state[draft_key][section],
        height=110, key=f"ta_{draft_key}_{section}",
    )

confirm = st.checkbox("Discard my edits and regenerate from current data")
if st.button("Regenerate", disabled=not confirm):
    st.session_state[draft_key] = sections
    for section in ("commit", "upside", "risk"):
        st.session_state.pop(f"ta_{draft_key}_{section}", None)
    st.rerun()

st.subheader("Largest open deals (challenge list)")
st.caption("Top open deals by amount — the commit/upside deals to pressure-test on the call. "
           "The flags column shows which already tripped a risk rule.")
st.dataframe(forecast.top_deals(current_id, flags=flags), width="stretch", hide_index=True)

st.subheader("Risk detail (coaching view)")
ui.risk_table(flags)
ui.deltas_expander(deltas)

st.subheader("Export")
md = narrative.assemble_markdown(edited, period=labels[current_id].split(" ")[0])
st.code(md, language="markdown")
st.download_button("Download .md", md, file_name="forecast_narrative.md")

st.caption("Draft — review before submitting. Read-only: nothing is sent anywhere.")
