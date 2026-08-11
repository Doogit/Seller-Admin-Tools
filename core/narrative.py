"""Deterministic narrative engine — templates in, three strings out.

No network, no API key, no adjectives without data behind them. Wording lives
in config/narrative_templates.yaml so it is editable without code changes.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from core.formatting import fmt_money

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATES = REPO_ROOT / "config" / "narrative_templates.yaml"

MOVEMENT_TYPES = ("moved stage", "amount changed", "slipped close_date")


def load_templates(path=None) -> dict:
    return yaml.safe_load(Path(path or DEFAULT_TEMPLATES).read_text(encoding="utf-8"))


def draft(
    rollup: dict,
    deltas: pd.DataFrame | None,
    flags: pd.DataFrame,
    prior_rollup: dict | None = None,
    quota: float | None = None,
    templates: dict | None = None,
) -> dict:
    """Returns {'commit': str, 'upside': str, 'risk': str}. Every number comes
    from the rollup/deltas/flags inputs verbatim through fmt_money."""
    t = templates or load_templates()

    # Commit
    ct = t["commit"]
    if prior_rollup is not None:
        diff = rollup["commit"] - prior_rollup["commit"]
        if diff > 0.005:
            wow = ct["wow_up"].format(delta=fmt_money(diff))
        elif diff < -0.005:
            wow = ct["wow_down"].format(delta=fmt_money(abs(diff)))
        else:
            wow = ct["wow_flat"]
    else:
        wow = ""
    commit = ct["base"].format(
        commit=fmt_money(rollup["commit"]), wow=wow, late_count=rollup["late_count"]
    )
    if quota:
        commit += ct["coverage"].format(
            quota=fmt_money(quota), coverage=f"{rollup['total_open'] / quota:.1f}"
        )
    if rollup.get("derived"):
        commit += ct["derived_note"]

    # Upside
    ut = t["upside"]
    upside = ut["base"].format(
        upside=fmt_money(rollup["upside"]), upside_count=rollup["upside_count"]
    )
    movers = pd.DataFrame(columns=["opportunity_name", "amount", "detail"])
    if deltas is not None and not deltas.empty:
        movers = (
            deltas[deltas["change_type"].isin(MOVEMENT_TYPES)]
            .sort_values("amount", ascending=False)
            .drop_duplicates(subset=["opportunity_name", "account_name"])
            .head(2)
        )
    if movers.empty:
        upside += ut["no_movers"]
    else:
        for _, m in movers.iterrows():
            upside += ut["mover"].format(
                name=m["opportunity_name"],
                amount=fmt_money(m["amount"]) if pd.notna(m["amount"]) else "$0",
                what=m["detail"],
            )

    # Risk
    rt = t["risk"]
    if flags is None or flags.empty:
        risk = rt["none"]
    else:
        unique = flags.drop_duplicates(subset=["opportunity_name", "account_name"])
        at_risk = float(unique["amount"].fillna(0).sum())
        risk = rt["base"].format(
            flag_count=len(unique), at_risk=fmt_money(at_risk)
        )
        top = flags.sort_values("amount", ascending=False).head(3)
        for _, f in top.iterrows():
            risk += rt["item"].format(
                name=f["opportunity_name"],
                amount=fmt_money(f["amount"]) if pd.notna(f["amount"]) else "$0",
                evidence=f["evidence"],
            )
        remainder = len(flags) - len(top)
        if remainder > 0:
            risk += rt["more"].format(n=remainder)

    return {"commit": commit, "upside": upside, "risk": risk}


def assemble_markdown(sections: dict, period: str = "") -> str:
    title = f"# Weekly forecast narrative{f' — {period}' if period else ''}"
    return (
        f"{title}\n\n"
        f"## Commit\n{sections['commit']}\n\n"
        f"## Upside\n{sections['upside']}\n\n"
        f"## Risk\n{sections['risk']}\n\n"
        "---\n*Draft — review before submitting. Read-only: nothing is sent anywhere.*\n"
    )
