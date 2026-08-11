"""Tool 1: weekly commit / upside / risk narrative draft."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st

from core import forecast, narrative, store
from core.formatting import fmt_money

st.set_page_config(page_title="Forecast Narrative", layout="wide")
st.title("Forecast narrative")

snaps = store.list_snapshots()
if snaps.empty:
    st.info("No snapshots yet — import a pipeline CSV on the Home page first.")
    st.stop()

labels = {
    int(r["id"]): f"{r['label']} (as of {r['as_of_date']}, {r['n_rows']} rows)"
    for _, r in snaps.iterrows()
}
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

at_risk = float(
    flags.drop_duplicates(subset=["opportunity_name", "account_name"])["amount"]
    .fillna(0).sum()
) if not flags.empty else 0.0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Commit", fmt_money(rollup["commit"]),
          delta=fmt_money(rollup["commit"] - prior_rollup["commit"]) if prior_rollup else None)
m2.metric("Upside", fmt_money(rollup["upside"]),
          delta=fmt_money(rollup["upside"] - prior_rollup["upside"]) if prior_rollup else None)
m3.metric("Coverage", f"{rollup['total_open'] / quota:.1f}x" if quota else "—")
m4.metric("At risk", fmt_money(at_risk))

if rollup.get("derived"):
    st.caption("Buckets derived from stage — map forecast_category for accuracy.")
if deltas is not None:
    n_unmatched = int((deltas["change_type"] == "unmatched").sum())
    if n_unmatched:
        st.warning(
            f"{n_unmatched} opportunities couldn't be matched to last week — "
            "renamed or ID missing? See the movement table."
        )

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

st.subheader("Risk detail (coaching view)")
for note in flags.attrs.get("notes", []):
    st.caption(f"Note: {note}")
if flags.empty:
    st.write("No risk flags.")
else:
    st.dataframe(flags, width="stretch", hide_index=True)

if deltas is not None and not deltas.empty:
    with st.expander("Week-over-week movement detail"):
        st.dataframe(deltas, width="stretch", hide_index=True)

st.subheader("Export")
md = narrative.assemble_markdown(edited, period=labels[current_id].split(" ")[0])
st.code(md, language="markdown")
st.download_button("Download .md", md, file_name="forecast_narrative.md")

st.caption("Draft — review before submitting. Read-only: nothing is sent anywhere.")
