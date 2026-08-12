"""Home view-model unit tests (green-suite gate). Exercises the reactive grid
model (mapping preview + stage buckets + validation) over the frozen pipeline
sample, plus the confirm-import strings and profile options. The sample
deliberately carries a negative amount, a malformed date, blank IDs and two
unmapped stages, so the validation/stage blocks have real content to assert."""

import datetime as dt

from core import ingest, mapping
from core.views import home as vm


def _df():
    return ingest.load_csv(vm.REPO_ROOT / "sample_data" / "energy_pipeline_sample.csv")


def _mapping():
    return vm.suggest_pipeline_mapping(list(_df().columns))


def test_suggest_maps_required_fields():
    m = _mapping()
    assert m["account_name"] == "Account"
    assert m["stage"] == "Sales Stage"
    assert m["amount"] == "Est. Revenue"
    assert m["close_date"] == "Close Dt"


def test_build_grid_happy_path():
    df, m = _df(), _mapping()
    grid = vm.build_grid(df, m, "auto", {}, vm.stage_map_defaults(), vm.alias_index())
    # mapping preview
    titles = [s["title"] for s in grid["preview"]["sections"]]
    assert titles == ["Required fields", "Optional fields"]
    assert grid["preview"]["missing_required"] == []
    assert grid["preview"]["date"]["resolved"] == "mdy"
    # stage block: the two off-map stages are flagged unknown
    stages = {r["raw"] for r in grid["stage"]["rows"]}
    assert {"Deal Review", "On Hold"} <= stages
    assert "Deal Review" in grid["stage"]["unknown"]
    assert dict((r["raw"], r["bucket"]) for r in grid["stage"]["rows"])["04 Commit"] == "late"
    # validation: sample has data-quality warnings but nothing blocking
    assert grid["validation"]["blocking"] == []
    assert grid["validation"]["warnings"]
    assert grid["blocked"] is False


def test_build_grid_missing_required_blocks():
    df = _df()
    grid = vm.build_grid(df, {}, "auto", {}, vm.stage_map_defaults(), None)
    assert set(grid["preview"]["missing_required"]) == set(
        ["account_name", "opportunity_name", "stage", "amount", "close_date", "owner"])
    assert grid["blocked"] is True
    assert grid["validation"]["blocking"][0].startswith(vm.REQUIRED_NOT_MAPPED)


def test_stage_preview_none_without_stage_field():
    df = _df()
    m = _mapping()
    m["stage"] = None
    assert vm.stage_preview(df, m, vm.stage_map_defaults(), {}) is None


def test_stage_chosen_overrides_default():
    df, m = _df(), _mapping()
    sp = vm.stage_preview(df, m, vm.stage_map_defaults(), {"On Hold": "late"})
    by_raw = {r["raw"]: r["bucket"] for r in sp["rows"]}
    assert by_raw["On Hold"] == "late"        # user choice wins over the (absent) default
    assert by_raw["04 Commit"] == "late"      # default still applied where unchosen


def test_stage_assignments_drops_blanks():
    rows = [{"raw": "A", "bucket": "early"}, {"raw": "B", "bucket": ""}]
    assert vm.stage_assignments_from(rows) == {"A": "early"}


def test_profile_options_and_default_label(db_path):
    assert vm.profile_options(db_path=db_path) == [vm.NEW_MAPPING]
    mapping.save_profile("Weekly export", {"account_name": "Account"},
                         {"prospecting": "early"}, "mdy", db_path=db_path)
    assert vm.profile_options(db_path=db_path) == [vm.NEW_MAPPING, "Weekly export"]
    assert vm.default_label(dt.date(2026, 8, 12)) == "wk33"


def test_confirm_strings():
    assert vm.import_success("wk33", 40, 18, 24_000_000.0) == (
        "Imported snapshot 'wk33': 40 rows, 18 accounts, $24,000,000 total pipeline.")
    dup = {"label": "wk32", "imported_at": "2026-08-05T09:00:00"}
    assert vm.duplicate_warning(dup).startswith("Already imported as 'wk32'")
