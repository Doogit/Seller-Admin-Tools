import pandas as pd

from core import importer, ingest, mapping, schema, store


def test_suggest_mapping_resolves_sample_headers(sample_path):
    headers = list(ingest.load_csv(sample_path).columns)
    suggestion = mapping.suggest_mapping(headers)
    for field in schema.REQUIRED_FIELDS:
        assert suggestion[field], f"required field {field} unresolved"
    assert suggestion["opportunity_id"] == "Opportunity ID"
    assert suggestion["amount"] == "Est. Revenue"
    assert suggestion["close_date"] == "Close Dt"
    assert suggestion["sub_vertical"] == "Sub-Vertical"
    assert suggestion["probability"] == "Probability (%)"


def test_profile_round_trip_zero_reselection(db_path, sample_mapping, stage_map):
    mapping.save_profile("weekly", sample_mapping, stage_map, "mdy", db_path=db_path)
    loaded = mapping.load_profiles(db_path=db_path)["weekly"]
    # Re-import with a saved profile needs zero manual selections: the loaded
    # profile must reproduce mapping, stage assignments, and date format exactly.
    assert loaded["mapping"] == sample_mapping
    assert loaded["stage_assignments"] == stage_map
    assert loaded["date_format"] == "mdy"


def test_snapshot_round_trip(db_path, sample_path, sample_mapping, stage_map, alias_index):
    result = importer.import_snapshot(
        sample_path, sample_mapping, "auto", stage_map, "wk32",
        db_path=db_path, alias_index=alias_index,
    )
    assert not result.skipped
    assert result.n_rows == 40
    df = store.get_opportunities(result.snapshot_id, db_path=db_path)
    assert len(df) == 40
    # alias/suffix normalization: Meridian counted once
    assert df[df["account_name"] == "meridian energy"]["account_name"].nunique() == 1
    assert df["account_name"].nunique() == 14
    # unmapped stages stored without a bucket and surfaced
    assert result.unmapped_stages == ["Deal Review", "On Hold"]
    assert (df["stage_bucket"] == "").sum() == 2


def test_duplicate_hash_requires_override(db_path, sample_path, sample_mapping, stage_map):
    first = importer.import_snapshot(
        sample_path, sample_mapping, "mdy", stage_map, "wk32", db_path=db_path
    )
    second = importer.import_snapshot(
        sample_path, sample_mapping, "mdy", stage_map, "wk33", db_path=db_path
    )
    assert second.skipped
    assert second.duplicate_of["label"] == "wk32"
    assert any("already imported" in w for w in second.warnings)
    forced = importer.import_snapshot(
        sample_path, sample_mapping, "mdy", stage_map, "wk33",
        on_duplicate="override", db_path=db_path,
    )
    assert not forced.skipped
    assert forced.snapshot_id != first.snapshot_id


def test_blocking_issue_writes_nothing(db_path, sample_path, sample_mapping, stage_map):
    broken = dict(sample_mapping, amount=None)
    result = importer.import_snapshot(
        sample_path, broken, "mdy", stage_map, "wk32", db_path=db_path
    )
    assert result.snapshot_id is None
    assert result.blocking
    assert store.list_snapshots(db_path=db_path).empty


def test_snapshots_append_only(db_path, sample_path, sample_mapping, stage_map):
    r1 = importer.import_snapshot(
        sample_path, sample_mapping, "mdy", stage_map, "wk32", db_path=db_path
    )
    r2 = importer.import_snapshot(
        sample_path, sample_mapping, "mdy", stage_map, "wk33",
        on_duplicate="override", db_path=db_path,
    )
    snaps = store.list_snapshots(db_path=db_path)
    assert len(snaps) == 2
    assert len(store.get_opportunities(r1.snapshot_id, db_path=db_path)) == 40
    assert len(store.get_opportunities(r2.snapshot_id, db_path=db_path)) == 40
