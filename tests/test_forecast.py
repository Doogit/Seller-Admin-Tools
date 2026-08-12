import datetime as dt

import pandas as pd
import pytest

from core import forecast, importer, narrative, store
from core.formatting import fmt_money


def opp(**kw):
    base = {
        "account_name": "acme power", "account_name_raw": "Acme Power",
        "opportunity_name": "Deal", "opportunity_id": "",
        "stage": "02 Develop", "stage_bucket": "mid",
        "amount": 100000.0, "close_date": "2026-12-01",
        "owner": "kevin dugas", "owner_raw": "Kevin Dugas",
        "forecast_category": None, "probability": None,
        "last_activity_date": None, "product": None, "sub_vertical": None,
        "exec_sponsor": None, "created_date": None,
    }
    base.update(kw)
    return base


def make_snapshot(db_path, rows, label, as_of):
    df = pd.DataFrame(rows)
    sid = store.create_snapshot(label, as_of, None, f"sha-{label}", db_path=db_path)
    store.insert_opportunities(sid, df, db_path=db_path)
    return sid


# --- rollup ---

def test_rollup_math_on_sample(db_path, sample_snapshot):
    rollup = forecast.bucket_rollup(sample_snapshot, db_path=db_path)
    # Hand-computed from the frozen sample CSV
    assert rollup["commit"] == 8_775_000.0
    assert rollup["upside"] == 6_330_000.0
    assert rollup["late_count"] == 6
    assert rollup["derived"] is True  # blank-category rows fall back to stage
    assert rollup["total_open"] == pytest.approx(
        rollup["commit"] + rollup["upside"] + rollup["pipeline"]
    )
    # closed_won (05 Closed Won) row excluded from open totals
    df = store.get_opportunities(sample_snapshot, db_path=db_path)
    open_sum = df[~df["stage_bucket"].isin(["closed_won", "closed_lost"])]["amount"].sum()
    assert rollup["total_open"] + rollup["unclassified"] == pytest.approx(open_sum)


# --- wow_delta ---

def test_wow_none_without_prior(db_path, sample_snapshot):
    assert forecast.wow_delta(sample_snapshot, None, db_path=db_path) is None


def test_renamed_opp_matches_on_id_not_new_disappeared(db_path):
    prior = make_snapshot(db_path, [opp(opportunity_id="X1", opportunity_name="Old Name")],
                          "w1", "2026-08-01")
    cur = make_snapshot(db_path, [opp(opportunity_id="X1", opportunity_name="New Name")],
                        "w2", "2026-08-08")
    deltas = forecast.wow_delta(cur, prior, db_path=db_path)
    assert not (deltas["change_type"] == "new").any()
    assert not (deltas["change_type"] == "disappeared").any()
    # totals move by $0: no amount-change rows either
    assert not (deltas["change_type"] == "amount changed").any()


def test_unmatched_bucket_when_no_id_and_names_diverge(db_path):
    prior = make_snapshot(db_path, [opp(opportunity_name="Alpha")], "w1", "2026-08-01")
    cur = make_snapshot(db_path, [opp(opportunity_name="Beta")], "w2", "2026-08-08")
    deltas = forecast.wow_delta(cur, prior, db_path=db_path)
    assert (deltas["change_type"] == "unmatched").sum() == 2  # one per side
    assert not (deltas["change_type"] == "new").any()
    assert not (deltas["change_type"] == "disappeared").any()


def test_mixed_id_and_name_matching(db_path):
    prior = make_snapshot(db_path, [
        opp(opportunity_id="A1", opportunity_name="ID Deal", stage="02 Develop"),
        opp(opportunity_name="Name Deal", amount=50000.0),
        opp(opportunity_id="G1", opportunity_name="Gone Deal"),
    ], "w1", "2026-08-01")
    cur = make_snapshot(db_path, [
        opp(opportunity_id="A1", opportunity_name="ID Deal", stage="03 Propose",
            stage_bucket="mid"),
        opp(opportunity_name="Name Deal", amount=75000.0),
        opp(opportunity_id="N1", opportunity_name="Brand New"),
        opp(opportunity_name="Mystery Deal"),
    ], "w2", "2026-08-08")
    deltas = forecast.wow_delta(cur, prior, db_path=db_path)
    by_type = deltas.groupby("change_type")["opportunity_name"].apply(list).to_dict()
    assert by_type["moved stage"] == ["ID Deal"]
    assert by_type["amount changed"] == ["Name Deal"]
    assert by_type["new"] == ["Brand New"]          # has ID -> trusted new
    assert by_type["disappeared"] == ["Gone Deal"]  # had ID -> trusted disappeared
    assert by_type["unmatched"] == ["Mystery Deal"]  # no ID, no name match


def test_duplicate_id_demotes_to_name_join(db_path):
    # Two rows share opportunity_id "D1" in both snapshots. Last-wins on the ID
    # key would cross-wire them and report phantom moves on an unchanged pair;
    # demoting duplicates to the name-join path pins each row to its true match.
    prior = make_snapshot(db_path, [
        opp(opportunity_id="D1", opportunity_name="Dup A", stage="02 Develop"),
        opp(opportunity_id="D1", opportunity_name="Dup B", stage="02 Develop"),
        opp(opportunity_id="U1", opportunity_name="Unique Deal", stage="02 Develop"),
    ], "w1", "2026-08-01")
    cur = make_snapshot(db_path, [
        opp(opportunity_id="D1", opportunity_name="Dup A", stage="02 Develop"),
        opp(opportunity_id="D1", opportunity_name="Dup B", stage="03 Propose",
            stage_bucket="mid"),
        opp(opportunity_id="U1", opportunity_name="Unique Deal", stage="02 Develop"),
    ], "w2", "2026-08-08")
    deltas = forecast.wow_delta(cur, prior, db_path=db_path)
    by_type = deltas.groupby("change_type")["opportunity_name"].apply(list).to_dict()
    assert by_type == {"moved stage": ["Dup B"]}  # only the real change, no phantoms


def test_duplicate_name_residuals_do_not_last_wins_match(db_path):
    # No-ID duplicate name keys are ambiguous in the same way duplicate IDs are:
    # last-wins would cross-wire the first current row to the second prior row
    # and report a false amount change.
    prior = make_snapshot(db_path, [
        opp(opportunity_name="Renewal", amount=100000.0),
        opp(opportunity_name="Renewal", amount=200000.0),
    ], "w1", "2026-08-01")
    cur = make_snapshot(db_path, [
        opp(opportunity_name="Renewal", amount=100000.0),
        opp(opportunity_name="Renewal", amount=200000.0),
    ], "w2", "2026-08-08")
    deltas = forecast.wow_delta(cur, prior, db_path=db_path)
    assert not (deltas["change_type"] == "amount changed").any()
    assert deltas["change_type"].tolist() == ["unmatched", "unmatched", "unmatched", "unmatched"]


def test_slip_detected(db_path):
    prior = make_snapshot(db_path, [opp(opportunity_id="S1", close_date="2026-09-30")],
                          "w1", "2026-08-01")
    cur = make_snapshot(db_path, [opp(opportunity_id="S1", close_date="2027-03-31")],
                        "w2", "2026-08-08")
    deltas = forecast.wow_delta(cur, prior, db_path=db_path)
    slipped = deltas[deltas["change_type"] == "slipped close_date"]
    assert len(slipped) == 1
    assert "2026-09-30 → 2027-03-31" in slipped.iloc[0]["detail"]


# --- risk flags ---

def test_stalled_fires_at_45_day_boundary(db_path):
    make_snapshot(db_path, [opp(opportunity_id="R1", stage="02 Develop")],
                  "w1", "2026-06-27")  # exactly 45 days before as-of
    cur = make_snapshot(db_path, [opp(opportunity_id="R1", stage="02 Develop")],
                        "w2", "2026-08-11")
    flags = forecast.risk_flags(cur, db_path=db_path)
    stalled = flags[flags["rule"] == "stalled"]
    assert len(stalled) == 1
    assert "45 days" in stalled.iloc[0]["evidence"]


def test_stalled_insufficient_history_reports_not_fires(db_path):
    make_snapshot(db_path, [opp(opportunity_id="R1", stage="02 Develop")],
                  "w1", "2026-07-12")  # 30 days observed
    cur = make_snapshot(db_path, [opp(opportunity_id="R1", stage="02 Develop")],
                        "w2", "2026-08-11")
    flags = forecast.risk_flags(cur, db_path=db_path)
    assert flags[flags["rule"] == "stalled"].empty
    assert any("insufficient history" in n for n in flags.attrs["notes"])


def test_stalled_silent_when_stage_advanced(db_path):
    make_snapshot(db_path, [opp(opportunity_id="R1", stage="02 Develop")],
                  "w1", "2026-06-01")  # 71 days back, but stage changed since
    cur = make_snapshot(db_path, [opp(opportunity_id="R1", stage="03 Propose")],
                        "w2", "2026-08-11")
    flags = forecast.risk_flags(cur, db_path=db_path)
    assert flags[flags["rule"] == "stalled"].empty
    assert not any("insufficient" in n for n in flags.attrs["notes"])


def test_no_sponsor_rule(db_path):
    cur = make_snapshot(db_path, [
        opp(opportunity_id="B1", amount=600000.0, exec_sponsor=""),
        opp(opportunity_id="B2", amount=600000.0, exec_sponsor="Jane Exec"),
        opp(opportunity_id="B3", amount=100000.0, exec_sponsor=""),
    ], "w1", "2026-08-11")
    flags = forecast.risk_flags(cur, db_path=db_path)
    hits = flags[flags["rule"] == "no_sponsor"]
    assert hits["opportunity_name"].tolist() == ["Deal"] and len(hits) == 1
    assert hits.iloc[0]["amount"] == 600000.0


def test_no_sponsor_skipped_when_unmapped(db_path):
    cur = make_snapshot(db_path, [opp(opportunity_id="B1", amount=900000.0)],
                        "w1", "2026-08-11")  # exec_sponsor None = unmapped
    flags = forecast.risk_flags(cur, db_path=db_path)
    assert flags[flags["rule"] == "no_sponsor"].empty
    assert any("exec_sponsor not mapped" in n for n in flags.attrs["notes"])


def test_big_and_late_rule(db_path):
    cur = make_snapshot(db_path, [
        opp(opportunity_id="L1", amount=1_200_000.0, close_date="2026-08-25",
            stage_bucket="mid"),
        opp(opportunity_id="L2", amount=1_200_000.0, close_date="2026-08-25",
            stage_bucket="late"),
        opp(opportunity_id="L3", amount=900_000.0, close_date="2026-08-25",
            stage_bucket="mid"),
        opp(opportunity_id="L4", amount=1_200_000.0, close_date="2026-12-01",
            stage_bucket="mid"),
    ], "w1", "2026-08-11")
    flags = forecast.risk_flags(cur, db_path=db_path)
    hits = flags[flags["rule"] == "big_and_late"]
    assert len(hits) == 1
    assert hits.iloc[0]["amount"] == 1_200_000.0
    assert "2026-08-25" in hits.iloc[0]["evidence"]


# --- narrative ---

def test_narrative_contains_rollup_numbers_verbatim(db_path, sample_snapshot):
    rollup = forecast.bucket_rollup(sample_snapshot, db_path=db_path)
    flags = forecast.risk_flags(sample_snapshot, db_path=db_path)
    sections = narrative.draft(rollup, None, flags)
    assert fmt_money(rollup["commit"]) in sections["commit"]
    assert str(rollup["late_count"]) in sections["commit"]
    assert fmt_money(rollup["upside"]) in sections["upside"]
    md = narrative.assemble_markdown(sections)
    for part in ("## Commit", "## Upside", "## Risk", "Draft — review"):
        assert part in md


def test_zero_row_snapshot_no_crash(db_path):
    """An empty snapshot (header-only import) must not KeyError through the
    session-3 analytics functions — get_opportunities carries columns even so."""
    sid = make_snapshot(db_path, [], "empty", "2026-08-11")
    assert forecast.bucket_rollup(sid, db_path=db_path)["total_open"] == 0.0
    assert forecast.stage_distribution(sid, db_path=db_path)["count"].sum() == 0
    assert forecast.top_deals(sid, db_path=db_path).empty
    assert forecast.owner_rollup(sid, db_path=db_path).empty
    assert forecast.risk_flags(sid, db_path=db_path).empty


def test_at_risk_total_dedups_and_handles_empty(db_path, sample_snapshot):
    flags = forecast.risk_flags(sample_snapshot, db_path=db_path)
    manual = (flags.drop_duplicates(subset=["opportunity_name", "account_name"])["amount"]
              .fillna(0).sum())
    assert forecast.at_risk_total(flags) == pytest.approx(manual)
    assert forecast.at_risk_total(flags.iloc[0:0]) == 0.0
    assert forecast.at_risk_total(None) == 0.0


# --- session-2 review fixes ---

def test_amount_change_emitted_when_one_side_blank(db_path):
    # A committed amount going to blank week-over-week is a real forecast swing,
    # not a non-event — it must surface as an "amount changed" row.
    prior = make_snapshot(db_path, [opp(opportunity_id="Z1", amount=500000.0)],
                          "w1", "2026-08-01")
    cur = make_snapshot(db_path, [opp(opportunity_id="Z1", amount=None)],
                        "w2", "2026-08-08")
    deltas = forecast.wow_delta(cur, prior, db_path=db_path)
    changed = deltas[deltas["change_type"] == "amount changed"]
    assert len(changed) == 1
    assert "(blank)" in changed.iloc[0]["detail"]


def test_risk_flags_demote_ambiguous_duplicate_ids(db_path):
    # Prior snapshot has two rows sharing id "X" (last-wins would pick the
    # stage-unchanged one and mis-fire stalled). Ambiguous keys are demoted.
    make_snapshot(db_path, [
        opp(opportunity_id="X", opportunity_name="Dup A", stage="03 Propose"),
        opp(opportunity_id="X", opportunity_name="Dup B", stage="02 Develop"),
    ], "w1", "2026-06-01")  # 71 days back
    cur = make_snapshot(db_path, [
        opp(opportunity_id="X", opportunity_name="Reconciled", stage="02 Develop"),
    ], "w2", "2026-08-11")
    flags = forecast.risk_flags(cur, db_path=db_path)
    assert flags[flags["rule"] == "stalled"].empty  # no trusted history -> no flag


def test_stalled_note_excludes_brand_new_opps(db_path):
    # OLD is seen-but-short (counts); NEW is absent from every prior (brand-new,
    # not "insufficient history").
    make_snapshot(db_path, [opp(opportunity_id="OLD", stage="02 Develop")],
                  "w1", "2026-07-12")  # 30 days observed
    cur = make_snapshot(db_path, [
        opp(opportunity_id="OLD", stage="02 Develop"),
        opp(opportunity_id="NEW", opportunity_name="Brand New", stage="02 Develop"),
    ], "w2", "2026-08-11")
    flags = forecast.risk_flags(cur, db_path=db_path)
    note = " ".join(flags.attrs["notes"])
    assert "insufficient history for 1 opportunities" in note


def test_at_risk_and_owner_distinguish_deals_sharing_a_name(db_path):
    # Two distinct flagged deals share account+opportunity name but differ by id
    # and owner. Name-only dedup would collapse them and undercount at-risk.
    cur = make_snapshot(db_path, [
        opp(opportunity_id="A1", account_name="acme", account_name_raw="Acme",
            opportunity_name="Renewal", amount=500000.0, exec_sponsor="",
            owner="kevin dugas"),
        opp(opportunity_id="A2", account_name="acme", account_name_raw="Acme",
            opportunity_name="Renewal", amount=600000.0, exec_sponsor="",
            owner="priya sharma"),
    ], "w1", "2026-08-11")
    flags = forecast.risk_flags(cur, db_path=db_path)
    assert len(flags[flags["rule"] == "no_sponsor"]) == 2
    assert forecast.at_risk_total(flags) == pytest.approx(1_100_000.0)
    rollup = forecast.owner_rollup(cur, db_path=db_path).set_index("owner")["at_risk"]
    assert rollup["kevin dugas"] == pytest.approx(500000.0)
    assert rollup["priya sharma"] == pytest.approx(600000.0)


def test_narrative_risk_dedups_multi_rule_opp(db_path):
    # One opportunity firing two rules must be counted and listed once, and the
    # "plus N more" remainder must not count the duplicate rule row.
    flags = pd.DataFrame([
        {"rule": "stalled", "opportunity_id": "A1", "opportunity_name": "Alpha",
         "account_name": "acme", "owner": "k", "amount": 900000.0, "evidence": "stalled"},
        {"rule": "slipped", "opportunity_id": "A1", "opportunity_name": "Alpha",
         "account_name": "acme", "owner": "k", "amount": 900000.0, "evidence": "slipped"},
        {"rule": "no_sponsor", "opportunity_id": "B2", "opportunity_name": "Beta",
         "account_name": "beta", "owner": "k", "amount": 300000.0, "evidence": "no sponsor"},
    ], columns=forecast.FLAG_COLUMNS)
    rollup = {"commit": 0.0, "upside": 0.0, "upside_count": 0, "late_count": 0,
              "total_open": 0.0}
    sections = narrative.draft(rollup, None, flags)
    assert "2 deal(s) flagged" in sections["risk"]
    assert sections["risk"].count("Alpha") == 1  # listed once, not per rule
    assert "more" not in sections["risk"]         # only 2 distinct deals, both shown


def test_narrative_unclassified_note(db_path):
    # An open deal in an unmapped stage with no forecast_category is excluded
    # from total_open; the narrative must say so rather than silently understate.
    sid = make_snapshot(db_path, [
        opp(opportunity_id="U1", stage="Mystery Stage", stage_bucket="",
            forecast_category=None, amount=750000.0),
    ], "w1", "2026-08-11")
    rollup = forecast.bucket_rollup(sid, db_path=db_path)
    assert rollup["unclassified"] == pytest.approx(750000.0)
    assert rollup["total_open"] == 0.0
    flags = forecast.risk_flags(sid, db_path=db_path)
    sections = narrative.draft(rollup, None, flags)
    assert "unmapped stages" in sections["commit"]


def test_top_deals_ties_broken_deterministically(db_path):
    # Equal amounts must order by account then opportunity name, not by
    # unstable sort — same snapshot, same order every run/platform.
    sid = make_snapshot(db_path, [
        opp(opportunity_id="T3", account_name="cephas", opportunity_name="Z", amount=100000.0),
        opp(opportunity_id="T1", account_name="acme", opportunity_name="Y", amount=100000.0),
        opp(opportunity_id="T2", account_name="beta", opportunity_name="X", amount=100000.0),
    ], "w1", "2026-08-11")
    names = forecast.top_deals(sid, db_path=db_path)["account_name"].tolist()
    assert names == ["acme", "beta", "cephas"]


def test_top_deals_accepts_precomputed_flags(db_path):
    # Reusing a precomputed flags frame must give the same result as computing
    # it internally (the QBR page passes one in to avoid recomputing risk_flags).
    cur = make_snapshot(db_path, [
        opp(opportunity_id="B1", amount=600000.0, exec_sponsor=""),
        opp(opportunity_id="B2", amount=200000.0, exec_sponsor="Jane Exec"),
    ], "w1", "2026-08-11")
    flags = forecast.risk_flags(cur, db_path=db_path)
    internal = forecast.top_deals(cur, db_path=db_path)
    reused = forecast.top_deals(cur, db_path=db_path, flags=flags)
    assert internal["flags"].tolist() == reused["flags"].tolist()
    assert (reused["flags"] == "no_sponsor").any()


def test_top_deals_uses_id_aware_flag_lookup(db_path):
    # Two distinct deals can share a name, but they must not inherit the same
    # risk labels by account+opportunity name alone.
    cur = make_snapshot(db_path, [
        opp(opportunity_id="A1", account_name="acme", opportunity_name="Renewal",
            amount=900000.0, exec_sponsor=""),
        opp(opportunity_id="A2", account_name="acme", opportunity_name="Renewal",
            amount=850000.0, exec_sponsor="Jane Exec"),
    ], "w1", "2026-08-11")
    flags = forecast.risk_flags(cur, db_path=db_path)
    top = forecast.top_deals(cur, db_path=db_path, flags=flags)
    assert top["flags"].tolist() == ["no_sponsor", ""]


def test_narrative_offline_socket_guard(db_path, sample_snapshot, monkeypatch):
    import socket

    def no_network(*args, **kwargs):
        raise AssertionError("network access attempted during narrative generation")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    rollup = forecast.bucket_rollup(sample_snapshot, db_path=db_path)
    flags = forecast.risk_flags(sample_snapshot, db_path=db_path)
    sections = narrative.draft(rollup, None, flags)
    assert sections["commit"] and sections["upside"] and sections["risk"]


def test_risk_flags_carry_coaching_action(db_path):
    # Every flag row carries the configured coaching ask so the manager sees the
    # one question to put to the rep, not just the evidence.
    cur = make_snapshot(db_path, [
        opp(opportunity_id="A1", opportunity_name="Renewal", amount=600000.0,
            exec_sponsor="", owner="kevin dugas"),
    ], "w1", "2026-08-11")
    flags = forecast.risk_flags(cur, db_path=db_path)
    assert "action" in forecast.FLAG_COLUMNS
    ns = flags[flags["rule"] == "no_sponsor"].iloc[0]
    assert ns["action"].strip()  # non-empty, sourced from risk_rules.yaml


def test_owner_rollup_accepts_precomputed_flags(db_path, sample_snapshot):
    # Passing flags in must match computing them internally (deck.gather threads
    # the single risk_flags pass through owner_rollup to avoid recompute).
    flags = forecast.risk_flags(sample_snapshot, db_path=db_path)
    passed = forecast.owner_rollup(sample_snapshot, db_path=db_path, flags=flags)
    internal = forecast.owner_rollup(sample_snapshot, db_path=db_path)
    pd.testing.assert_frame_equal(passed, internal)


def test_snapshot_trend_orders_and_filters(db_path):
    w1 = make_snapshot(db_path, [opp(opportunity_id="A1", amount=100000.0)],
                       "w1", "2026-07-01")
    make_snapshot(db_path, [opp(opportunity_id="A1", amount=200000.0)],
                  "w2", "2026-08-01")
    tr = forecast.snapshot_trend(db_path=db_path)
    assert list(tr.columns) == forecast.TREND_COLUMNS
    assert tr["as_of_date"].tolist() == ["2026-07-01", "2026-08-01"]
    # through_id caps the trend at that snapshot's as-of — never a future week
    tr1 = forecast.snapshot_trend(db_path=db_path, through_id=w1)
    assert tr1["as_of_date"].tolist() == ["2026-07-01"]


def test_stalled_evidence_shows_threshold(db_path):
    make_snapshot(db_path, [opp(opportunity_id="R1", stage="02 Develop")],
                  "w1", "2026-06-27")
    cur = make_snapshot(db_path, [opp(opportunity_id="R1", stage="02 Develop")],
                        "w2", "2026-08-11")
    flags = forecast.risk_flags(cur, db_path=db_path)
    assert "flags at 45" in flags[flags["rule"] == "stalled"].iloc[0]["evidence"]


def test_commit_conversion_counts_and_rate(db_path):
    # Prior week: two commit deals (late stage -> commit) and one upside deal.
    prior = make_snapshot(db_path, [
        opp(opportunity_id="C1", stage_bucket="late", forecast_category="commit"),
        opp(opportunity_id="C2", stage_bucket="late", forecast_category="commit"),
        opp(opportunity_id="U1", stage_bucket="mid", forecast_category="upside"),
    ], "w1", "2026-07-01")
    # This week: C1 won, C2 lost, U1 (not a prior commit) irrelevant.
    cur = make_snapshot(db_path, [
        opp(opportunity_id="C1", stage_bucket="closed_won"),
        opp(opportunity_id="C2", stage_bucket="closed_lost"),
        opp(opportunity_id="U1", stage_bucket="mid"),
    ], "w2", "2026-08-01")
    cc = forecast.commit_conversion(cur, prior, db_path=db_path)
    assert cc["prior_commit_count"] == 2
    assert cc["won"] == 1 and cc["lost"] == 1
    assert cc["landed_rate"] == pytest.approx(0.5)


def test_commit_conversion_none_without_prior(db_path, sample_snapshot):
    assert forecast.commit_conversion(sample_snapshot, None, db_path=db_path) is None
