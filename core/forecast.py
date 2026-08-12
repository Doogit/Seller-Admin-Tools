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
FLAG_COLUMNS = ["rule", "opportunity_name", "account_name", "owner", "amount", "evidence",
                "opportunity_id"]


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


def _name_key(account, opportunity):
    """Normalized name join key. One definition, used by both _keys and the
    wow_delta name-join residual pass, so the two never drift."""
    return "name::" + account + "||" + opportunity


def _keys(df: pd.DataFrame) -> pd.Series:
    """Row-level match key: opportunity_id when non-empty, else normalized
    (account_name, opportunity_name) — precedence pinned in docs/PLAN.md."""
    ids = df["opportunity_id"]
    names = _name_key(df["account_name"], df["opportunity_name"])
    return ids.where(ids != "", names)


def dedup_flags(flags: pd.DataFrame) -> pd.DataFrame:
    """One row per flagged opportunity, ID-aware. Distinct deals that share an
    account/opportunity name but carry different opportunity_ids are kept apart
    — name-only dedup would collapse them and undercount at-risk."""
    if flags is None or flags.empty:
        return flags
    if "opportunity_id" in flags.columns:
        keep = ~_keys(flags).duplicated()
    else:
        keep = ~flags.duplicated(subset=["account_name", "opportunity_name"])
    return flags[keep]


def _open_with_category(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """Open rows with a `category` column resolved per-row: forecast_category
    when populated, else derived from stage bucket. Second value is True when
    any open row used the stage fallback."""
    open_df = df[~df["stage_bucket"].isin(CLOSED_BUCKETS)].copy()
    cat = open_df["forecast_category"].str.lower()
    from_stage = open_df["stage_bucket"].map(STAGE_TO_CATEGORY)
    open_df["category"] = cat.where(cat.isin(CATEGORY_VALUES), from_stage)
    derived = bool(((~cat.isin(CATEGORY_VALUES)) & from_stage.notna()).any())
    return open_df, derived


def bucket_rollup(snapshot_id: int, db_path=None) -> dict:
    """Commit / upside / pipeline totals for one snapshot.

    Per-row precedence: forecast_category when populated, else derived from the
    stage bucket (late->commit, mid->upside, early->pipeline). `derived` is True
    when any open row used the stage fallback.
    """
    df = _clean(store.get_opportunities(snapshot_id, db_path=db_path))
    open_df, derived = _open_with_category(df)

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
    # Duplicate non-empty IDs within a snapshot can't be trusted as a join key
    # (last-wins would cross-wire rows), so demote them to the name-join path.
    cur_dup = set(cur_ids[(cur_ids != "") & cur_ids.duplicated(keep=False)])
    pri_dup = set(pri_ids[(pri_ids != "") & pri_ids.duplicated(keep=False)])
    pri_by_id = {v: i for i, v in pri_ids.items() if v and v not in pri_dup}
    matches: list[tuple[int, int]] = []
    matched_pri: set[int] = set()
    unmatched_cur: list[int] = []

    for i, cid in cur_ids.items():
        if cid and cid not in cur_dup and cid in pri_by_id \
                and pri_by_id[cid] not in matched_pri:
            matches.append((i, pri_by_id[cid]))
            matched_pri.add(pri_by_id[cid])
        else:
            unmatched_cur.append(i)

    def name_key(df, i):
        return _name_key(df.at[i, "account_name"], df.at[i, "opportunity_name"])

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
        c_na, p_na = pd.isna(c["amount"]), pd.isna(p["amount"])
        if not (c_na and p_na):
            # A swing to/from a blank amount is a real forecast move — treat the
            # blank side as $0 for the delta rather than silently dropping it.
            c_amt = 0.0 if c_na else float(c["amount"])
            p_amt = 0.0 if p_na else float(p["amount"])
            if abs(c_amt - p_amt) > 0.005:
                p_disp = "(blank)" if p_na else fmt_money(p_amt)
                c_disp = "(blank)" if c_na else fmt_money(c_amt)
                add("amount changed", cur, ci, f"{p_disp} → {c_disp}")
        if c["close_date"] and p["close_date"] and c["close_date"] > p["close_date"]:
            days = (dt.date.fromisoformat(c["close_date"])
                    - dt.date.fromisoformat(p["close_date"])).days
            add("slipped close_date", cur, ci,
                f"close date moved {p['close_date']} → {c['close_date']} (+{days}d)")

    for i in still_unmatched_cur:
        if cur_ids[i] and cur_ids[i] not in cur_dup:
            add("new", cur, i, "not present last week")
        else:
            add("unmatched", cur, i,
                "no opportunity_id and no name match in prior snapshot — renamed or ID missing?")
    for i in pri.index:
        if i in matched_pri:
            continue
        if pri_ids[i] and pri_ids[i] not in pri_dup:
            add("disappeared", pri, i, "present last week, gone this week")
        else:
            add("unmatched", pri, i,
                "prior-week row with no opportunity_id and no name match this week")

    return pd.DataFrame(rows, columns=DELTA_COLUMNS)


BUCKET_ORDER = ["early", "mid", "late", "closed_won", "closed_lost", "unmapped"]


def stage_distribution(snapshot_id: int, prior_id: int | None = None, db_path=None) -> pd.DataFrame:
    """Count + $ per stage bucket, with week-over-week deltas when a prior
    snapshot is given. Buckets ordered early -> closed; unmapped last."""
    def dist(sid):
        df = _clean(store.get_opportunities(sid, db_path=db_path))
        bucket = df["stage_bucket"].where(df["stage_bucket"] != "", "unmapped")
        g = df.assign(bucket=bucket).groupby("bucket")
        return pd.DataFrame({"count": g.size(), "amount": g["amount"].sum()})

    out = dist(snapshot_id).reindex(BUCKET_ORDER).fillna(0)
    if prior_id is not None:
        prior = dist(prior_id).reindex(BUCKET_ORDER).fillna(0)
        out["delta_count"] = out["count"] - prior["count"]
        out["delta_amount"] = out["amount"] - prior["amount"]
    out.index.name = "bucket"
    return out.reset_index()


def top_deals(snapshot_id: int, n: int = 10, db_path=None) -> pd.DataFrame:
    """Top open deals by amount with risk-flag names joined."""
    df = _clean(store.get_opportunities(snapshot_id, db_path=db_path))
    open_df = df[~df["stage_bucket"].isin(CLOSED_BUCKETS)]
    top = open_df.sort_values(
        ["amount", "account_name", "opportunity_name"], ascending=[False, True, True]
    ).head(n)
    flags = risk_flags(snapshot_id, db_path=db_path)
    flag_map: dict[tuple, list[str]] = {}
    for _, f in flags.iterrows():
        flag_map.setdefault((f["opportunity_name"], f["account_name"]), []).append(f["rule"])
    out = top[["opportunity_name", "account_name", "stage", "amount", "close_date", "owner"]].copy()
    out["flags"] = [
        ", ".join(flag_map.get((r["opportunity_name"], r["account_name"]), []))
        for _, r in top.iterrows()
    ]
    return out.reset_index(drop=True)


def owner_rollup(snapshot_id: int, db_path=None) -> pd.DataFrame:
    """Per-seller commit / upside / pipeline / at-risk. Groups on the
    alias-normalized owner column written at import time, so spelling variants
    of one seller roll up as one row."""
    df = _clean(store.get_opportunities(snapshot_id, db_path=db_path))
    open_df, _ = _open_with_category(df)
    flags = risk_flags(snapshot_id, db_path=db_path)
    flagged = dedup_flags(flags)
    at_risk = flagged.groupby("owner")["amount"].sum() if not flagged.empty else pd.Series(dtype="float64")

    rows = []
    for owner, g in open_df.groupby("owner"):
        amounts = g["amount"].fillna(0)
        rows.append({
            "owner": owner,
            "commit": float(amounts[g["category"] == "commit"].sum()),
            "upside": float(amounts[g["category"] == "upside"].sum()),
            "pipeline": float(amounts[g["category"] == "pipeline"].sum()),
            "deals": len(g),
            "at_risk": float(at_risk.get(owner, 0.0)),
        })
    return pd.DataFrame(
        rows, columns=["owner", "commit", "upside", "pipeline", "deals", "at_risk"]
    ).sort_values("commit", ascending=False).reset_index(drop=True)


def at_risk_total(flags: pd.DataFrame) -> float:
    """Sum of flagged amounts, one row per opportunity (ID-aware dedup). Single
    source for both the QBR deck scorecard and the page metric row so they never
    diverge."""
    if flags is None or flags.empty:
        return 0.0
    return float(dedup_flags(flags)["amount"].fillna(0).sum())


def sub_vertical_split(snapshot_id: int, db_path=None) -> pd.DataFrame | None:
    """Open pipeline by sub-vertical; None when the field is unmapped."""
    raw = store.get_opportunities(snapshot_id, db_path=db_path)
    if raw.empty or raw["sub_vertical"].isna().all():
        return None
    df = _clean(raw)
    open_df = df[~df["stage_bucket"].isin(CLOSED_BUCKETS)]
    sv = open_df["sub_vertical"].where(open_df["sub_vertical"] != "", "(blank)")
    g = open_df.assign(sub_vertical=sv).groupby("sub_vertical")
    out = pd.DataFrame({"count": g.size(), "amount": g["amount"].sum()})
    return out.sort_values("amount", ascending=False).reset_index()


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
        fkeys = _keys(frame)
        # Duplicate keys within a prior snapshot are ambiguous — dropping them
        # (rather than last-wins) avoids comparing a current row against an
        # arbitrary namesake, the same discipline wow_delta uses.
        dup = set(fkeys[fkeys.duplicated(keep=False)])
        keymap = {k: i for i, k in fkeys.items() if k not in dup}
        priors.append((dt.date.fromisoformat(srow["as_of_date"]), frame, keymap))

    open_df = cur[~cur["stage_bucket"].isin(CLOSED_BUCKETS)]
    cur_keys = _keys(cur)
    cur_dup = set(cur_keys[cur_keys.duplicated(keep=False)])

    def add(rule, row, evidence):
        flags.append({
            "rule": rule,
            "opportunity_id": row["opportunity_id"],
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
        if key in cur_dup:
            continue  # ambiguous identity this week — can't trace its history
        same_stage_since = cur_as_of
        observed_since = cur_as_of
        moved = False
        seen = False
        for as_of, frame, keymap in priors:
            j = keymap.get(key)
            if j is None:
                break
            seen = True
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
        elif seen and not moved and observed < threshold:
            # Seen before but not long enough to judge. Brand-new deals (never
            # in any prior) are simply new, not "insufficient history".
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
            key = cur_keys[i]
            if key in cur_dup:
                continue
            j = pkeymap.get(key)
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
