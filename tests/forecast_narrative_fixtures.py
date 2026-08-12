"""Shared synthetic snapshots for the Forecast Narrative view + parity tests.

One definition, imported by both the golden-capture (`goldens/.../capture.py`)
and the parity/view tests, so the frozen goldens and the assertions exercise
byte-identical inputs. Mirrors tests/test_forecast.py's `opp` / `make_snapshot`
style (synthetic frames, tmp DBs — no reliance on the demo data/agents.db).

Three scenarios per the plan's parity matrix:
  full    — prior + current with every note/flag/movement class + a quota.
  minimal — one snapshot, optional fields unmapped (skip-notes), no prior/quota.
  empty   — a zero-row (header-only) snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from core import store


def opp(**kw) -> dict:
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


def _make(db_path, rows, label, as_of) -> int:
    df = pd.DataFrame(rows)
    sid = store.create_snapshot(label, as_of, None, f"sha-{label}", db_path=db_path)
    store.insert_opportunities(sid, df, db_path=db_path)
    return sid


@dataclass(frozen=True)
class Scenario:
    key: str
    current_id: int
    prior_id: int | None
    quota: float | None
    current_label: str


def build_full(db_path) -> Scenario:
    prior = _make(db_path, [
        opp(opportunity_id="A1", opportunity_name="Renewal Alpha", stage="02 Develop",
            stage_bucket="mid", amount=900000.0, close_date="2026-09-30",
            exec_sponsor="Jane Exec", owner="kevin dugas"),
        opp(opportunity_id="A2", opportunity_name="Expansion Beta", stage="02 Develop",
            stage_bucket="mid", amount=500000.0, close_date="2026-10-15",
            exec_sponsor="", owner="priya sharma"),
        opp(opportunity_name="Legacy Gamma", stage="01 Qualify", stage_bucket="early",
            amount=50000.0, close_date="2026-11-01", exec_sponsor="Sam Sponsor",
            owner="kevin dugas"),
        opp(opportunity_id="G1", opportunity_name="Gone Deal", stage="03 Propose",
            stage_bucket="late", amount=300000.0, close_date="2026-09-15",
            exec_sponsor="Jane Exec", owner="priya sharma"),
    ], "wk31", "2026-06-27")
    current = _make(db_path, [
        # unchanged stage since prior (45 days) -> stalled; close slipped -> slipped
        opp(opportunity_id="A1", opportunity_name="Renewal Alpha", stage="02 Develop",
            stage_bucket="mid", amount=900000.0, close_date="2026-11-30",
            exec_sponsor="Jane Exec", owner="kevin dugas"),
        # moved stage + amount changed + blank sponsor (no_sponsor)
        opp(opportunity_id="A2", opportunity_name="Expansion Beta", stage="03 Propose",
            stage_bucket="late", amount=750000.0, close_date="2026-10-15",
            exec_sponsor="", owner="priya sharma"),
        # has id, absent from prior -> new; big + closing soon + not late -> big_and_late
        opp(opportunity_id="N1", opportunity_name="Fresh Delta", stage="01 Qualify",
            stage_bucket="early", amount=1500000.0, close_date="2026-08-20",
            exec_sponsor="", owner="kevin dugas"),
        # unmapped stage bucket -> unclassified; no id + no name match -> unmatched
        opp(opportunity_name="Mystery Epsilon", stage="Custom Stage", stage_bucket="",
            amount=750000.0, close_date="2026-10-01", exec_sponsor="Al Exec",
            owner="priya sharma"),
    ], "wk32", "2026-08-11")
    return Scenario("full", current, prior, 5_000_000.0, "wk32")


def build_minimal(db_path) -> Scenario:
    # Optional fields unmapped (None) -> no_sponsor skipped; no prior -> slipped
    # skipped, deltas None, coverage "—".
    sid = _make(db_path, [
        opp(opportunity_id="M1", opportunity_name="Simple Deal", stage="02 Develop",
            stage_bucket="mid", amount=200000.0, close_date="2026-12-01",
            exec_sponsor=None, owner="kevin dugas"),
    ], "wkmin", "2026-08-11")
    return Scenario("minimal", sid, None, None, "wkmin")


def build_empty(db_path) -> Scenario:
    sid = _make(db_path, [], "wkempty", "2026-08-11")
    return Scenario("empty", sid, None, None, "wkempty")


# key -> builder. Each builder writes ONE self-contained scenario; callers must
# give each its OWN db_path (sharing a db leaks sibling snapshots with the same
# as_of_date into risk_flags' prior-chain walk). See capture.py / the parity test.
BUILDERS = {
    "full": build_full,
    "minimal": build_minimal,
    "empty": build_empty,
}
