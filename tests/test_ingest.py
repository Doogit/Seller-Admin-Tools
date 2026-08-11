import pandas as pd
import pytest

from core import ingest, schema


def test_load_csv_tolerates_bom_and_semicolons():
    data = "﻿Account;Amount\nAcme;100\n".encode("utf-8")
    df = ingest.load_csv(data)
    assert list(df.columns) == ["Account", "Amount"]
    assert df.iloc[0]["Account"] == "Acme"


def test_parse_amounts_currency_and_negatives():
    s = pd.Series(["$1,234.00", "($15,000.00)", "", "750000"])
    values, problems = ingest.parse_amount_series(s)
    assert values.tolist()[:2] == [1234.0, -15000.0]
    assert pd.isna(values.iloc[2])
    assert values.iloc[3] == 750000.0
    assert problems == []


def test_parse_amounts_junk_reported_not_dropped():
    values, problems = ingest.parse_amount_series(pd.Series(["TBD"]))
    assert pd.isna(values.iloc[0])
    assert len(problems) == 1


def test_mixed_currency_symbols_warn_and_proceed():
    values, problems = ingest.parse_amount_series(pd.Series(["$100.00", "€200.00"]))
    assert values.tolist() == [100.0, 200.0]
    assert any("currency" in p.lower() for p in problems)


def test_ambiguous_date_differs_by_format():
    s = pd.Series(["03/04/2026"])
    mdy, _ = ingest.parse_date_series(s, "mdy")
    dmy, _ = ingest.parse_date_series(s, "dmy")
    assert mdy.iloc[0] == "2026-03-04"
    assert dmy.iloc[0] == "2026-04-03"


def test_malformed_date_reported():
    parsed, unparsed = ingest.parse_date_series(pd.Series(["13/32/2026"]), "mdy")
    assert parsed.iloc[0] == ""
    assert unparsed.iloc[0] == "13/32/2026"


def test_iso_dates_accepted_under_any_format():
    parsed, _ = ingest.parse_date_series(pd.Series(["2026-09-30"]), "dmy")
    assert parsed.iloc[0] == "2026-09-30"


def test_auto_infers_mdy_from_unambiguous_values():
    cols = [pd.Series(["9/25/2026", "03/04/2026"])]
    assert ingest.infer_date_format(cols) == "mdy"


def test_auto_infers_dmy():
    assert ingest.infer_date_format([pd.Series(["25/9/2026"])]) == "dmy"


def test_auto_conflicting_evidence_raises():
    with pytest.raises(ingest.ConflictingDateFormat):
        ingest.infer_date_format([pd.Series(["9/25/2026", "25/9/2026"])])


def test_auto_all_ambiguous_raises():
    with pytest.raises(ingest.AmbiguousDateFormat):
        ingest.infer_date_format([pd.Series(["03/04/2026", "1/2/2026"])])


def test_auto_samples_all_date_columns_jointly():
    close = pd.Series(["03/04/2026"])          # ambiguous alone
    created = pd.Series(["25/9/2025"])          # dmy evidence
    assert ingest.infer_date_format([close, created]) == "dmy"


def test_normalize_name_strips_suffixes():
    assert ingest.normalize_name("Meridian Energy Corp") == "meridian energy"
    assert ingest.normalize_name("Meridian Energy") == "meridian energy"


def test_normalize_name_alias_lookup(alias_index):
    assert ingest.normalize_name("Meridian Energy Holdings", alias_index) == "meridian energy"


def test_apply_mapping_full_sample(sample_path, sample_mapping, alias_index):
    df = ingest.load_csv(sample_path)
    canonical, problems, resolved = ingest.apply_mapping(
        df, sample_mapping, "auto", alias_index=alias_index
    )
    assert resolved == "mdy"
    assert len(canonical) == 40
    assert canonical["amount"].dtype.kind == "f"
    # Meridian Energy + Meridian Energy Corp unify
    meridian = canonical[canonical["account_name"] == "meridian energy"]
    assert set(meridian["account_name_raw"]) == {"Meridian Energy", "Meridian Energy Corp"}
    # malformed date surfaced, not dropped
    assert (canonical["close_date_unparsed"] == "13/32/2026").sum() == 1
    # validation flags the negative amount and blank IDs as warnings only
    issues = schema.validate_frame(canonical)
    severities = {i["severity"] for i in issues}
    assert severities == {schema.WARNING}
    assert any("Negative amount" in i["message"] for i in issues)
    assert any("lack opportunity_id" in i["message"] for i in issues)


def test_european_decimal_comma_normalized():
    s = pd.Series(["€1.234,56", "1234,56", "$1,234.00", "$1.234.567,89"])
    values, _ = ingest.parse_amount_series(s)
    assert values.tolist() == [1234.56, 1234.56, 1234.0, 1234567.89]


def test_cp1252_fallback():
    data = "Account,Amount\nCafé Energie,100\n".encode("cp1252")
    df = ingest.load_csv(data)
    assert df.iloc[0]["Account"] == "Café Energie"


def test_empty_file_raises_friendly_error():
    with pytest.raises(ingest.IngestError, match="empty"):
        ingest.load_csv(b"")


def test_duplicate_headers_after_strip_raise():
    with pytest.raises(ingest.IngestError, match="Duplicate column"):
        ingest.load_csv(b"Amount ,Amount\n1,2\n")


def test_day_over_31_is_not_format_evidence():
    # '05/45/2026' is junk, not month-first evidence; the ambiguous value
    # must still force an explicit choice.
    with pytest.raises(ingest.AmbiguousDateFormat):
        ingest.infer_date_format([pd.Series(["05/45/2026", "03/04/2026"])])


def test_no_recognizable_dates_raises():
    with pytest.raises(ingest.AmbiguousDateFormat):
        ingest.infer_date_format([pd.Series(["Jan 5, 2026", "TBD"])])


def test_validate_frame_missing_required_blocks():
    df = pd.DataFrame({"account_name": ["a"]})
    issues = schema.validate_frame(df)
    assert any(i["severity"] == schema.BLOCKING for i in issues)
