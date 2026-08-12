"""View model for tool 2 (QBR Assembler).

Backed by a single core.deck.gather pass (the same analytics the .pptx/.md
downloads use, so on-screen numbers can't disagree with the deck). Downloads
reuse core.deck **unchanged** — streamed by the route, not rebuilt here. Pure:
no web/Streamlit imports. Shared strings/formatting come from core.views.common.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    stage: dict
    sub_vertical: dict | None
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
        stage=_stage(data),
        sub_vertical=_sub_vertical(data),
        top=_top(data),
        risk=common.risk_block(data["flags"]),
        safe_period=safe_period(period),
    )
