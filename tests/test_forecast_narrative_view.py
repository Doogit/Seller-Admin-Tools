"""View-model unit tests for tool 1 (green-suite gate; distinct from the Task 4
parity golden). Exercises happy path, missing-optional degradation, empty data,
and each conditional note, asserting the exact user-facing strings the route
renders verbatim."""

import pandas as pd

import forecast_narrative_fixtures as fx

from core import forecast
from core.views import forecast_narrative as vm


# --- full: happy path with every note/flag/movement class ---

def test_full_metrics_strings(db_path):
    sc = fx.build_full(db_path)
    v = vm.build(sc.current_id, sc.prior_id, sc.quota, db_path=db_path)
    assert v.metrics["commit"] == "$750K"
    assert v.metrics["upside"] == "$900K"
    assert v.metrics["at_risk"] == "$3.1M"  # 3 deduped deals: 1.5M + 900K + 750K
    assert v.metrics["coverage"] == "0.6x"
    assert v.metrics["commit_delta"] == "$450K"
    assert v.metrics["upside_delta"] is not None
    assert v.metrics["derived_note"] == vm.DERIVED_NOTE
    assert v.metrics["unclassified_note"] == (
        "$750K open in unmapped stages is excluded from coverage."
    )


def test_full_unmatched_warning(db_path):
    sc = fx.build_full(db_path)
    v = vm.build(sc.current_id, sc.prior_id, sc.quota, db_path=db_path)
    assert v.unmatched["n"] == 2
    assert v.unmatched["warning"] == (
        "2 opportunities couldn't be matched to last week — "
        "renamed or ID missing? See the movement table."
    )


def test_singular_unmatched_warning():
    # n=1 is the bug the plural fix targets: "1 opportunity", not "opportunities"
    w = vm._unmatched(pd.DataFrame({"change_type": ["unmatched"]}))["warning"]
    assert w == (
        "1 opportunity couldn't be matched to last week — "
        "renamed or ID missing? See the movement table."
    )


def test_full_risk_and_movement_tables(db_path):
    sc = fx.build_full(db_path)
    v = vm.build(sc.current_id, sc.prior_id, sc.quota, db_path=db_path)
    # risk table present, opportunity_id column dropped, amount money-formatted
    assert v.risk["empty_text"] is None
    assert "opportunity_id" not in v.risk["columns"]
    # 'action' relabelled to 'suggested ask' (the coaching ask); id dropped
    assert v.risk["columns"] == [
        "rule", "opportunity_name", "account_name", "owner", "amount", "evidence",
        "suggested ask",
    ]
    assert v.risk["rows"] and all(
        r["amount"].startswith("$") for r in v.risk["rows"] if r["amount"]
    )
    # movement detail present with the pinned delta columns
    assert v.movement["columns"] == forecast.DELTA_COLUMNS
    assert v.movement["rows"]


def test_full_challenge_list(db_path):
    sc = fx.build_full(db_path)
    v = vm.build(sc.current_id, sc.prior_id, sc.quota, db_path=db_path)
    # largest open deals, amount money-formatted, risk-flag names joined
    assert v.challenge["rows"]
    assert v.challenge["columns"][:4] == ["opportunity_name", "account_name", "stage", "amount"]
    assert "flags" in v.challenge["columns"]
    assert all(r["amount"].startswith("$") for r in v.challenge["rows"] if r["amount"])


def test_full_draft_matches_generator_and_period(db_path):
    sc = fx.build_full(db_path)
    v = vm.build(sc.current_id, sc.prior_id, sc.quota, db_path=db_path)
    regenerated = vm.draft_sections(sc.current_id, sc.prior_id, sc.quota, db_path=db_path)
    assert v.draft == regenerated
    assert set(v.draft) == set(vm.SECTIONS)
    assert v.period == "wk32"


# --- minimal: optional fields unmapped, no prior ---

def test_minimal_degrades_without_prior_or_optional_fields(db_path):
    sc = fx.build_minimal(db_path)
    v = vm.build(sc.current_id, sc.prior_id, sc.quota, db_path=db_path)
    assert v.metrics["coverage"] == vm.COVERAGE_EMPTY  # "—", no quota
    assert v.metrics["commit_delta"] is None            # no prior
    assert v.metrics["upside_delta"] is None
    assert v.metrics["derived_note"] == vm.DERIVED_NOTE  # forecast_category unmapped
    assert v.unmatched == {"n": 0, "warning": None}      # deltas None
    assert v.movement["rows"] == []
    assert v.risk["empty_text"] == vm.NO_RISK_FLAGS
    assert v.risk["rows"] == []


def test_minimal_skip_notes_present(db_path):
    sc = fx.build_minimal(db_path)
    v = vm.build(sc.current_id, sc.prior_id, sc.quota, db_path=db_path)
    assert "Note: slipped: no prior snapshot — rule skipped." in v.risk["notes"]
    assert "Note: no_sponsor: exec_sponsor not mapped — rule skipped." in v.risk["notes"]


# --- empty: zero-row snapshot ---

def test_empty_snapshot_renders_zeros(db_path):
    sc = fx.build_empty(db_path)
    v = vm.build(sc.current_id, sc.prior_id, sc.quota, db_path=db_path)
    assert v.metrics["commit"] == "$0"
    assert v.metrics["coverage"] == vm.COVERAGE_EMPTY
    assert v.risk["empty_text"] == vm.NO_RISK_FLAGS
    assert set(v.draft) == set(vm.SECTIONS)
    assert all(v.draft[s] for s in vm.SECTIONS)


# --- selection helpers + empty-state ---

def test_snapshot_options_and_default_selection(db_path):
    fx.build_full(db_path)  # writes wk31 (prior) + wk32 (current)
    options = vm.snapshot_options(db_path=db_path)
    labels = [lbl for _, lbl in options]
    assert any(lbl.startswith("wk32 (as of 2026-08-11, 4 rows)") for lbl in labels)
    current, prior = vm.default_selection(options)
    assert current == options[0][0]      # most recent first
    assert prior == options[1][0]        # next most recent
    # single snapshot -> no prior
    assert vm.default_selection(options[:1]) == (options[0][0], None)


def test_empty_state_when_no_snapshots(db_path):
    assert vm.snapshot_options(db_path=db_path) == []
    assert vm.default_selection([]) == (None, None)
    assert vm.EMPTY_STATE == "No snapshots yet — import a pipeline CSV on the Home page first."
