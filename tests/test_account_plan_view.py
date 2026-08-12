"""Account-Plan view-model unit tests (green-suite gate; distinct from the Task
13 parity golden). Happy path (Meridian + pipeline), no-pipeline degradation,
minimal (all-gap) footprint, the reactive import-grid preview, and the
zero-pipeline-match alias path."""

import account_plan_fixtures as afx

from core import crosswalk, ingest
from core.views import account_plan as vm


def test_full_scenario_plan(db_path):
    sc = afx.build_full(db_path)
    v = vm.build(sc.account_name, sc.snapshot_id, db_path=db_path)
    assert v.account_display == "Meridian Energy"
    assert v.metrics == {"whitespace": "$820,000", "uncovered": 3, "obligations": 8}
    # landed/partial/gap mix present, each status glyph-prefixed
    statuses = {r["status"] for r in v.gaps["rows"]}
    assert any(s.startswith("🟢") for s in statuses)   # landed
    assert any(s.startswith("🟡") for s in statuses)   # partial
    assert any(s.startswith("🔴") for s in statuses)   # gap
    assert v.gaps["empty_text"] is None
    assert v.pipeline["rows"] and "amount" in v.pipeline["columns"]
    assert v.zero_match is None
    assert v.relationship_map == "(fill in — relationship map stays human)"
    assert v.disclaimer  # obligation-map disclaimer surfaced
    assert v.safe_name == "meridian_energy"


def test_no_pipeline_scenario(db_path):
    sc = afx.build_no_pipeline(db_path)
    v = vm.build(sc.account_name, sc.snapshot_id, db_path=db_path)
    assert v.metrics["whitespace"] == "$0"
    assert v.pipeline["rows"] == []
    assert v.zero_match is None
    # uncovered gaps still computed from the crosswalk (no pipeline to net out)
    assert v.metrics["uncovered"] >= 1


def test_minimal_all_gap(db_path):
    sc = afx.build_minimal(db_path)
    v = vm.build(sc.account_name, sc.snapshot_id, db_path=db_path)
    assert v.account_display == "Cascade Power & Light"
    # empty footprint -> no landed/partial, everything is a gap
    assert all(r["status"].startswith("🔴") for r in v.gaps["rows"])
    assert v.gaps["empty_text"] is None


def test_empty_scope_shows_no_obligations():
    # account with no regulatory_scope -> gap_table empty -> NO_OBLIGATIONS text
    gaps = crosswalk.gap_table({"account_name": "x"})
    block = vm._gaps_block(gaps)
    assert block["rows"] == []
    assert block["empty_text"] == vm.NO_OBLIGATIONS


def test_import_preview(sample_path):
    df = ingest.load_csv(afx.FACTS_CSV.read_bytes())
    m = vm.suggest_facts_mapping(list(df.columns))
    preview = vm.import_preview(df, m, "auto")
    titles = [s["title"] for s in preview["sections"]]
    assert titles == ["Required fields", "Optional fields"]
    # required account_name + sub_vertical auto-mapped, with live samples
    req = {f["field"]: f for f in preview["sections"][0]["fields"]}
    assert req["account_name"]["selected"] == "Account Name"
    assert req["account_name"]["samples"][0] == "Meridian Energy"
    assert preview["missing_required"] == []
    # date preview parses the Agreement End column under the inferred format
    assert preview["date"]["resolved"] == "mdy"
    assert {"raw": "6/30/2027", "parsed": "2027-06-30"} in preview["date"]["rows"]


def test_import_preview_missing_required():
    df = ingest.load_csv(afx.FACTS_CSV.read_bytes())
    preview = vm.import_preview(df, {}, "auto")  # nothing mapped
    assert set(preview["missing_required"]) == {"account_name", "sub_vertical"}
    assert preview["date"] is None  # no date field mapped


def test_zero_pipeline_match_offers_alias(db_path):
    # Gulf Stream Petroleum (facts) vs Gulfstream Petroleum (pipeline): a spelling
    # difference -> zero direct match, near-name candidate offered.
    sc = afx.build_full(db_path)  # seeds facts + pipeline once
    from core import store
    gs = store.load_account_facts(db_path=db_path)
    name = gs.loc[gs["account_name_raw"] == "Gulf Stream Petroleum", "account_name"].iloc[0]
    v = vm.build(name, sc.snapshot_id, db_path=db_path)
    assert v.zero_match is not None
    assert "matches zero pipeline rows" in v.zero_match["warning"]
    assert v.zero_match["candidates"] == ["gulfstream petroleum"]
    assert v.zero_match["no_candidates_text"] is None


def test_options_and_categories(db_path):
    afx.build_full(db_path)
    assert vm.has_facts(db_path=db_path) is True
    opts = dict(vm.account_options(db_path=db_path))
    assert opts["meridian energy"] == "Meridian Energy"
    cats = vm.product_assign_categories()
    assert cats == sorted(cats) and "siem" in cats
    assert vm.FOOTER.endswith("nothing is sent anywhere.")
