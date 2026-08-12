"""View model for tool 2 (QBR Assembler).

Backed by a single core.deck.gather pass (the same analytics the .pptx/.md
downloads use, so on-screen numbers can't disagree with the deck). Downloads
reuse core.deck **unchanged** — streamed by the route, not rebuilt here. Pure:
no web/Streamlit imports. Shared strings/formatting come from core.views.common.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from core import deck, store
from core.views import common
from core.views.common import (  # re-exported for the route
    COVERAGE_EMPTY, EMPTY_STATE, NO_RISK_FLAGS, PRIOR_NONE_LABEL,
    default_selection, snapshot_options,
)

# Tool-2 verbatim strings (inventory §1b).
NUMBERS_IDENTICAL = "Numbers identical to Forecast Narrative for the same snapshot."
SUBVERTICAL_UNAVAILABLE = (
    "Sub-vertical split unavailable — field not mapped in this snapshot.")
FOOTER = "Draft — review before presenting. Read-only: nothing is sent anywhere."
DEFAULT_TEAM = "Energy Team"
OWNER_EMPTY = "No open pipeline by owner."
TREND_CAPTION = "Commit / upside / at-risk across weekly snapshots up to the selected one."

OPEN_EXCLUDE = ("closed_won", "closed_lost")


@dataclass(frozen=True)
class QbrView:
    snapshot_options: list[tuple[int, str]]
    prior_options: list[tuple[int, str]]
    current_id: int
    prior_id: int | None
    period: str
    team: str
    quota: float | None
    metrics: dict
    credibility: str | None
    trend: dict | None
    stage: dict
    sub_vertical: dict | None
    owner: dict
    top: dict
    risk: dict
    safe_period: str


def default_period(db_path=None) -> str:
    """Most-recent snapshot's raw label — the page's `snaps.iloc[0]["label"]`."""
    snaps = store.list_snapshots(db_path=db_path)
    return "" if snaps.empty else str(snaps.iloc[0]["label"])


def safe_period(period: str) -> str:
    return (period or "qbr").replace(" ", "_")


def _stage(data: dict) -> dict:
    """Open-bucket bars for the on-screen chart (single series, like the page's
    st.bar_chart of open_dist['amount']). Rendering is out of parity scope; the
    values trace to forecast.stage_distribution."""
    dist = data["stage_dist"]
    open_dist = dist[~dist["bucket"].isin(OPEN_EXCLUDE)]
    amounts = [float(a) for a in open_dist["amount"]]
    top = max(amounts) if amounts else 0.0
    bars = [
        {
            "bucket": str(b),
            "amount": a,
            "amount_str": common.money_cell(a),
            "pct": round(a / top * 100) if top > 0 else 0,
        }
        for b, a in zip(open_dist["bucket"], amounts)
    ]
    return {"bars": bars, "empty": not any(a > 0 for a in amounts)}


def _sub_vertical(data: dict) -> dict | None:
    sv = data["sub_vertical"]
    if sv is None:
        return None
    return {"columns": list(sv.columns), "rows": common.table_rows(sv)}


def _top(data: dict) -> dict:
    top = data["top"]
    return {"columns": list(top.columns), "rows": common.table_rows(top)}


def _money_rows(df, money_cols: tuple[str, ...]) -> list[dict]:
    """Records with the named columns money-formatted (tables are out of byte-
    parity scope; the values still trace to core.forecast)."""
    out = []
    for rec in df.to_dict("records"):
        row = {k: ("" if pd.isna(v) else v) for k, v in rec.items()}
        for c in money_cols:
            if c in rec:
                row[c] = common.money_cell(rec[c])
        out.append(row)
    return out


def _owner(data: dict) -> dict:
    """Per-seller commit/upside/pipeline/at-risk (forecast.owner_rollup)."""
    o = data["owner_rollup"]
    if o is None or o.empty:
        return {"columns": [], "rows": [], "empty_text": OWNER_EMPTY}
    return {"columns": list(o.columns),
            "rows": _money_rows(o, ("commit", "upside", "pipeline", "at_risk")),
            "empty_text": None}


def _trend(data: dict) -> dict | None:
    """Multi-week commit/upside/at-risk trend — shown only with >=2 snapshots
    (matches the page's `len(trend) >= 2` guard)."""
    t = data["trend"]
    if t is None or len(t) < 2:
        return None
    return {"columns": list(t.columns),
            "rows": _money_rows(t, ("commit", "upside", "at_risk"))}


def build(current_id: int, prior_id: int | None, period: str, team: str,
          quota: float | None, db_path=None) -> QbrView:
    meta = {"period": period, "team": team, "quota": quota or None}
    data = deck.gather(current_id, prior_id, meta, db_path=db_path)
    options = snapshot_options(db_path=db_path)
    prior_options = [o for o in options if o[0] != current_id]
    return QbrView(
        snapshot_options=options,
        prior_options=prior_options,
        current_id=current_id,
        prior_id=prior_id,
        period=period,
        team=team,
        quota=quota,
        metrics=common.metric_block(data["rollup"], data["prior_rollup"], quota,
                                    data["at_risk"]),
        credibility=deck.credibility_summary(data["commit_conversion"]),
        trend=_trend(data),
        stage=_stage(data),
        sub_vertical=_sub_vertical(data),
        owner=_owner(data),
        top=_top(data),
        risk=common.risk_block(data["flags"]),
        safe_period=safe_period(period),
    )
