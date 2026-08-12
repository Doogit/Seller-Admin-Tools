"""QBR view-model unit tests (green-suite gate; distinct from the parity golden).
Happy path (sample CSV), with-prior degradation-of-optionals, and empty data."""

import qbr_fixtures as qfx

from core.views import qbr as vm


def test_sample_scorecard_matches_forecast_numbers(db_path):
    sc = qfx.build_sample(db_path)
    v = vm.build(sc.current_id, sc.prior_id, sc.period, sc.team, sc.quota, db_path=db_path)
    # identical to the Forecast Narrative metrics for this snapshot
    assert v.metrics["commit"] == "$8.8M"
    assert v.metrics["upside"] == "$6.3M"
    assert v.metrics["coverage"] == vm.COVERAGE_EMPTY  # no quota
    assert v.metrics["at_risk"] == "$750K"


def test_sample_stage_subvertical_top_risk(db_path):
    sc = qfx.build_sample(db_path)
    v = vm.build(sc.current_id, sc.prior_id, sc.period, sc.team, sc.quota, db_path=db_path)
    assert not v.stage["empty"] and v.stage["bars"]
    assert all(0 <= b["pct"] <= 100 for b in v.stage["bars"])
    # sub-vertical mapped in the sample -> table present, not the 'unavailable' note
    assert v.sub_vertical is not None
    assert v.sub_vertical["columns"] == ["sub_vertical", "count", "amount"]
    assert v.top["columns"][:4] == ["opportunity_name", "account_name", "stage", "amount"]
    assert len(v.top["rows"]) == 10
    assert v.risk["empty_text"] is None and v.risk["rows"]
    assert "opportunity_id" not in v.risk["columns"]


def test_prior_scenario_arrows_coverage_and_no_subvertical(db_path):
    sc = qfx.build_prior(db_path)
    v = vm.build(sc.current_id, sc.prior_id, sc.period, sc.team, sc.quota, db_path=db_path)
    assert v.metrics["coverage"].endswith("x")          # quota given
    assert v.metrics["commit_delta"] is not None        # prior present
    assert v.sub_vertical is None                        # -> route shows SUBVERTICAL_UNAVAILABLE


def test_empty_snapshot(db_path):
    sc = qfx.build_empty(db_path)
    v = vm.build(sc.current_id, sc.prior_id, sc.period, sc.team, sc.quota, db_path=db_path)
    assert v.stage["empty"] is True
    assert v.metrics["commit"] == "$0"
    assert v.risk["empty_text"] == "No risk flags."
    assert v.top["rows"] == []
    assert v.sub_vertical is None


def test_defaults_and_safe_period(db_path):
    qfx.build_sample(db_path)  # writes wk32
    assert vm.default_period(db_path=db_path) == "wk32"
    assert vm.safe_period("Q3 FY26") == "Q3_FY26"
    assert vm.safe_period("") == "qbr"
    assert vm.DEFAULT_TEAM == "Energy Team"
    assert vm.SUBVERTICAL_UNAVAILABLE.startswith("Sub-vertical split unavailable")
