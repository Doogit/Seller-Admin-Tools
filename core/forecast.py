"""Pipeline analytics: bucket rollups, week-over-week deltas, risk flags.

Pure functions over stored snapshots — no Streamlit imports. Tools 1 (forecast
narrative) and 2 (QBR assembler) both read from here so their numbers always
agree.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import yaml

from core import store
from core.formatting import fmt_money

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RULES = REPO_ROOT / "config" / "risk_rules.yaml"

CLOSED_BUCKETS = {"closed_won", "closed_lost"}
CATEGORY_VALUES = {"commit", "upside", "pipeline"}
STAGE_TO_CATEGORY = {"late": "commit", "mid": "upside", "early": "pipeline"}

DELTA_COLUMNS = ["change_type", "opportunity_name", "account_name", "owner", "amount", "detail"]
FLAG_COLUMNS = ["rule", "opportunity_name", "account_name", "owner", "amount", "evidence"]


def _load_rules(rules_path=None) -> dict:
    return yaml.safe_load(Path(rules_path or DEFAULT_RULES).read_text(encoding="utf-8"))


def _snapshot_as_of(snapshot_id: int, db_path=None) -> dt.date:
    snaps = store.list_snapshots(db_path=db_path)
    row = snaps[snaps["id"] == snapshot_id]
    if row.empty:
        raise ValueError(f"Unknown snapshot id {snapshot_id}")
    return dt.date.fromisoformat(row.iloc[0]["as_of_date"])


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ("stage", "stage_bucket", "opportunity_id", "account_name",
                "opportunity_name", "close_date", "forecast_category",
                "exec_sponsor", "owner"):
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
    return df


def _keys(df: pd.DataFrame) -> pd.Series:
    """Row-level match key: opportunity_id when non-empty, else normalized
    (account_name, opportunity_name) — precedence pinned in docs/PLAN.md."""
    ids = df["opportunity_id"]
    names = "name::" + df["account_name"] + "||" + df["opportunity_name"]
    return ids.where(ids != "", names)


def bucket_rollup(snapshot_id: int, db_path=None) -> dict:
    """Commit / upside / pipeline totals for one snapshot.

    Per-row precedence: forecast_category when populated, else derived from the
    stage bucket (late->commit, mid->upside, early->pipeline). `derived` is True
    when any open row used the stage fallback.
    """
    df = _clean(store.get_opportunities(snapshot_id, db_path=db_path))
    open_df = df[~df["stage_bucket"].isin(CLOSED_BUCKETS)].copy()

    cat = open_df["forecast_category"].str.lower()
    from_stage = open_df["stage_bucket"].map(STAGE_TO_CATEGORY)
    resolved = cat.where(cat.isin(CATEGORY_VALUES), from_stage)
    derived = bool(((~cat.isin(CATEGORY_VALUES)) & from_stage.notna()).any())
    open_df["category"] = resolved

    amounts = open_df["amount"].fillna(0)
    result = {"derived": derived}
    for bucket in ("commit", "upside", "pipeline"):
        mask = open_df["category"] == bucket
        result[bucket] = float(amounts[mask].sum())
        result[f"{bucket}_count"] = int(mask.sum())
    unclassified = open_df["category"].isna()
    result["unclassified"] = float(amounts[unclassified].sum())
    result["unclassified_count"] = int(unclassified.sum())
    result["total_open"] = result["commit"] + result["upside"] + result["pipeline"]
    result["late_count"] = int((open_df["stage_bucket"] == "late").sum())
    return result


def wow_delta(current_id: int, prior_id: int | None, db_path=None) -> pd.DataFrame | None:
    """Classify week-over-week movement. Returns None when no prior snapshot.

    Matching (pinned semantics): rows with a non-empty opportunity_id join on
    ID; residuals join on normalized names. After both passes, an unmatched row
    WITH an ID is genuinely new/disappeared (trust the key); an unmatched row
    WITHOUT an ID goes to the `unmatched` bucket — never silently new+disappeared.
    """
    if prior_id is None:
        return None
    cur = _clean(store.get_opportunities(current_id, db_path=db_path))
    pri = _clean(store.get_opportunities(prior_id, db_path=db_path))
    if cur.empty or pri.empty:
        return None

    cur_ids = cur["opportunity_id"]
    pri_ids = pri["opportunity_id"]
    pri_by_id = {v: i for i, v in pri_ids.items() if v}
    matches: list[tuple[int, int]] = []
    matched_pri: set[int] = set()
    unmatched_cur: list[int] = []

    for i, cid in cur_ids.items():
        if cid and cid in pri_by_id and pri_by_id[cid] not in matched_pri:
            matches.append((i, pri_by_id[cid]))
            matched_pri.add(pri_by_id[cid])
        else:
            unmatched_cur.append(i)

    def name_key(df, i):
        return df.at[i, "account_name"] + "||" + df.at[i, "opportunity_name"]

    pri_by_name = {
        name_key(pri, i): i for i in pri.index
        if i not in matched_pri
    }
    still_unmatched_cur = []
    for i in unmatched_cur:
        j = pri_by_name.get(name_key(cur, i))
        if j is not None and j not in matched_pri:
            matches.append((i, j))
            matched_pri.add(j)
        else:
            still_unmatched_cur.append(i)

    rows: list[dict] = []

    def add(change_type, df, i, detail):
        rows.append({
            "change_type": change_type,
            "opportunity_name": df.at[i, "opportunity_name"],
            "account_name": df.at[i, "account_name"],
            "owner": df.at[i, "owner"],
            "amount": df.at[i, "amount"],
            "detail": detail,
        })

    for ci, pi in matches:
        c, p = cur.loc[ci], pri.loc[pi]
        if c["stage"] != p["stage"]:
            add("moved stage", cur, ci, f"{p['stage']} → {c['stage']}")
        c_amt = c["amount"] if pd.notna(c["amount"]) else None
        p_amt = p["amount"] if pd.notna(p["amount"]) else None
        if c_amt is not None and p_amt is not None and abs(c_amt - p_amt) > 0.005:
            add("amount changed", cur, ci, f"{fmt_money(p_amt)} → {fmt_money(c_amt)}")
        if c["close_date"] and p["close_date"] and c["close_date"] > p["close_date"]:
            days = (dt.date.fromisoformat(c["close_date"])
                    - dt.date.fromisoformat(p["close_date"])).days
            add("slipped close_date", cur, ci,
                f"close date moved {p['close_date']} → {c['close_date']} (+{days}d)")

    for i in still_unmatched_cur:
        if cur_ids[i]:
            add("new", cur, i, "not present last week")
        else:
            add("unmatched", cur, i,
                "no opportunity_id and no name match in prior snapshot — renamed or ID missing?")
    for i in pri.index:
        if i in matched_pri:
            continue
        if pri_ids[i]:
            add("disappeared", pri, i, "present last week, gone this week")
        else:
            add("unmatched", pri, i,
                "prior-week row with no opportunity_id and no name match this week")

    return pd.DataFrame(rows, columns=DELTA_COLUMNS)


def risk_flags(snapshot_id: int, db_path=None, rules_path=None) -> pd.DataFrame:
    """Rule-based risk flags with evidence strings. Non-firing rules that
    cannot be evaluated (insufficient history, unmapped field) surface in
    df.attrs['notes'] instead of staying silent."""
    rules = _load_rules(rules_path)
    cur_as_of = _snapshot_as_of(snapshot_id, db_path=db_path)
    cur = _clean(store.get_opportunities(snapshot_id, db_path=db_path))
    notes: list[str] = []
    flags: list[dict] = []

    snaps = store.list_snapshots(db_path=db_path)
    prior_chain = snaps[
        (snaps["id"] != snapshot_id)
        & (snaps["as_of_date"] <= cur_as_of.isoformat())
    ].sort_values(["as_of_date", "id"], ascending=False)
    priors: list[tuple[dt.date, dict]] = []
    for _, srow in prior_chain.iterrows():
        frame = _clean(store.get_opportunities(int(srow["id"]), db_path=db_path))
        if frame.empty:
            continue
        keymap = {k: i for i, k in _keys(frame).items()}
        priors.append((dt.date.fromisoformat(srow["as_of_date"]), frame, keymap))

    open_df = cur[~cur["stage_bucket"].isin(CLOSED_BUCKETS)]
    cur_keys = _keys(cur)

    def add(rule, row, evidence):
        flags.append({
            "rule": rule,
            "opportunity_name": row["opportunity_name"],
            "account_name": row["account_name"],
            "owner": row["owner"],
            "amount": row["amount"],
            "evidence": evidence,
        })

    # stalled — walk snapshots backward per opportunity (consecutive run)
    threshold = int(rules["stalled"]["min_days_in_stage"])
    insufficient = 0
    max_observed = 0
    for i, row in open_df.iterrows():
        key = cur_keys[i]
        same_stage_since = cur_as_of
        observed_since = cur_as_of
        moved = False
        for as_of, frame, keymap in priors:
            j = keymap.get(key)
            if j is None:
                break
            observed_since = as_of
            if frame.at[j, "stage"] == row["stage"]:
                same_stage_since = as_of
            else:
                moved = True
                break
        age = (cur_as_of - same_stage_since).days
        observed = (cur_as_of - observed_since).days
        if age >= threshold:
            add("stalled", row,
                f"in stage '{row['stage']}' for {age} days (since {same_stage_since})")
        elif not moved and observed < threshold:
            insufficient += 1
            max_observed = max(max_observed, observed)
    if insufficient:
        notes.append(
            f"stalled: insufficient history for {insufficient} opportunities "
            f"({max_observed} days observed, need {threshold})."
        )

    # slipped — vs the immediately prior snapshot
    slip_days = int(rules["slipped"]["min_days_slip"])
    if priors:
        _, pframe, pkeymap = priors[0]
        for i, row in open_df.iterrows():
            j = pkeymap.get(cur_keys[i])
            if j is None:
                continue
            c_close, p_close = row["close_date"], pframe.at[j, "close_date"]
            if c_close and p_close:
                delta = (dt.date.fromisoformat(c_close) - dt.date.fromisoformat(p_close)).days
                if delta >= slip_days:
                    add("slipped", row, f"close date moved {p_close} → {c_close} (+{delta}d)")
    else:
        notes.append("slipped: no prior snapshot — rule skipped.")

    # no_sponsor — skip when the field is unmapped (stored as all-NULL)
    min_amount = float(rules["no_sponsor"]["min_amount"])
    if store.get_opportunities(snapshot_id, db_path=db_path)["exec_sponsor"].isna().all():
        notes.append("no_sponsor: exec_sponsor not mapped — rule skipped.")
    else:
        big = open_df[(open_df["amount"].fillna(0) >= min_amount) & (open_df["exec_sponsor"] == "")]
        for _, row in big.iterrows():
            add("no_sponsor", row,
                f"no exec sponsor on a {fmt_money(row['amount'])} deal")

    # big_and_late — big deal closing soon (or overdue) but not late-stage
    min_big = float(rules["big_and_late"]["min_amount"])
    within = int(rules["big_and_late"]["within_days"])
    horizon = (cur_as_of + dt.timedelta(days=within)).isoformat()
    candidates = open_df[
        (open_df["amount"].fillna(0) >= min_big)
        & (open_df["close_date"] != "")
        & (open_df["close_date"] <= horizon)
        & (open_df["stage_bucket"] != "late")
    ]
    for _, row in candidates.iterrows():
        add("big_and_late", row,
            f"{fmt_money(row['amount'])} closing {row['close_date']} "
            f"but stage is '{row['stage']}' (bucket: {row['stage_bucket'] or 'unmapped'})")

    out = pd.DataFrame(flags, columns=FLAG_COLUMNS)
    out.attrs["notes"] = notes
    return out
