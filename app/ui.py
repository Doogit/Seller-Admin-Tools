"""Shared Streamlit render helpers for pages 1-3."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core import forecast
from core.formatting import fmt_money


def snapshot_labels(snaps: pd.DataFrame) -> dict[int, str]:
    return {
        int(r["id"]): f"{r['label']} (as of {r['as_of_date']}, {r['n_rows']} rows)"
        for _, r in snaps.iterrows()
    }


def metric_row(rollup: dict, prior_rollup: dict | None, quota: float | None,
               at_risk: float) -> None:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Commit", fmt_money(rollup["commit"]),
              delta=fmt_money(rollup["commit"] - prior_rollup["commit"])
              if prior_rollup else None)
    m2.metric("Upside", fmt_money(rollup["upside"]),
              delta=fmt_money(rollup["upside"] - prior_rollup["upside"])
              if prior_rollup else None)
    m3.metric("Coverage", f"{rollup['total_open'] / quota:.1f}x" if quota else "—")
    m4.metric("At risk", fmt_money(at_risk))
    if rollup.get("derived"):
        st.caption("Buckets derived from stage — map forecast_category for accuracy.")
    if rollup.get("unclassified_count"):
        st.caption(
            f"{fmt_money(rollup['unclassified'])} open in unmapped stages is "
            "excluded from coverage."
        )


def risk_table(flags: pd.DataFrame) -> None:
    for note in flags.attrs.get("notes", []):
        st.caption(f"Note: {note}")
    if flags.empty:
        st.write("No risk flags.")
    else:
        st.dataframe(flags.drop(columns=["opportunity_id"], errors="ignore"),
                     width="stretch", hide_index=True)


def deltas_expander(deltas: pd.DataFrame | None) -> None:
    if deltas is not None and not deltas.empty:
        with st.expander("Week-over-week movement detail"):
            st.dataframe(deltas, width="stretch", hide_index=True)


def unmatched_warning(deltas: pd.DataFrame | None) -> None:
    if deltas is None:
        return
    n = int((deltas["change_type"] == "unmatched").sum())
    if n:
        st.warning(
            f"{n} opportunities couldn't be matched to last week — "
            "renamed or ID missing? See the movement table."
        )
