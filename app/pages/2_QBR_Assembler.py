"""Tool 2: QBR review package — on-screen view + .pptx/.md downloads."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
for p in (str(REPO_ROOT), str(REPO_ROOT / "app")):
    if p not in sys.path:
        sys.path.insert(0, p)

import streamlit as st

import ui
from core import deck, forecast, store

st.set_page_config(page_title="QBR Assembler", layout="wide")
st.title("QBR assembler")

snaps = store.list_snapshots()
if snaps.empty:
    st.info("No snapshots yet — import a pipeline CSV on the Home page first.")
    st.stop()

labels = ui.snapshot_labels(snaps)
ids = list(labels)

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    current_id = st.selectbox("Snapshot", ids, index=0, format_func=labels.get)
prior_options = [i for i in ids if i != current_id]
with c2:
    prior_id = st.selectbox(
        "Prior snapshot", [None] + prior_options,
        index=1 if prior_options else 0,
        format_func=lambda i: "— none —" if i is None else labels[i],
    )
with c3:
    period = st.text_input("Period label", value=snaps.iloc[0]["label"])
with c4:
    team = st.text_input("Team / segment", value="Energy Team")
with c5:
    quota = st.number_input("Quota (optional)", min_value=0.0, value=0.0,
                            step=100000.0, format="%.0f")

meta = {"period": period, "team": team, "quota": quota or None}

rollup = forecast.bucket_rollup(current_id)
prior_rollup = forecast.bucket_rollup(prior_id) if prior_id else None
flags = forecast.risk_flags(current_id)

ui.metric_row(rollup, prior_rollup, quota or None, ui.at_risk_total(flags))
st.caption("Numbers identical to Forecast Narrative for the same snapshot.")

st.subheader("Pipeline by stage")
dist = forecast.stage_distribution(current_id, prior_id)
open_dist = dist[~dist["bucket"].isin(["closed_won", "closed_lost"])]
st.bar_chart(open_dist.set_index("bucket")["amount"])

sv = forecast.sub_vertical_split(current_id)
if sv is None:
    st.caption("Sub-vertical split unavailable — field not mapped in this snapshot.")
else:
    st.subheader("Sub-vertical split")
    st.dataframe(sv, width="stretch", hide_index=True)

st.subheader("Top deals")
st.dataframe(forecast.top_deals(current_id), width="stretch", hide_index=True)

st.subheader("Risks")
ui.risk_table(flags)

st.subheader("Downloads")
stamp = dt.date.today().strftime("%Y%m%d")
safe_period = (period or "qbr").replace(" ", "_")
pptx_buf = deck.build_pptx(current_id, prior_id, meta)
md_text = deck.build_md(current_id, prior_id, meta)
d1, d2 = st.columns(2)
with d1:
    st.download_button(
        "Download .pptx", pptx_buf, file_name=f"qbr_{safe_period}_{stamp}.pptx",
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
with d2:
    st.download_button("Download .md appendix", md_text,
                       file_name=f"qbr_{safe_period}_{stamp}.md")

st.caption("Draft — review before presenting. Read-only: nothing is sent anywhere.")
