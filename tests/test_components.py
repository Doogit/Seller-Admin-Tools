"""Unit tests for the shared presentational components (web/components.py):
the status-chip tone mapping and data_table's optional chip column. Structural
only — no view-model strings are produced here; tone selection is presentation."""

from fasthtml.common import to_xml

from web.components import _chip, data_table


def test_chip_tone_selects_okabe_ito_classes():
    pos = to_xml(_chip("landed", "positive"))
    assert "bg-positive-tint" in pos and "text-positive-ink" in pos and "bg-positive" in pos
    med = to_xml(_chip("partial", "medium"))
    assert "bg-medium-tint" in med and "text-medium-ink" in med


def test_chip_default_and_unknown_tone_fall_back_to_high():
    assert "bg-high-tint" in to_xml(_chip("stalled"))       # default tone
    assert "bg-high-tint" in to_xml(_chip("x", "bogus"))    # unknown tone -> high


def test_chip_always_carries_the_literal_word_and_a_dot():
    # colorblind-safe: meaning never by color alone
    html = to_xml(_chip("gap", "high"))
    assert "gap" in html and "rounded-sm" in html  # literal word + the dot span


def test_data_table_chip_tone_maps_values_else_high():
    rows = [{"status": "landed"}, {"status": "gap"}, {"status": "other"}]
    html = to_xml(data_table(["status"], rows, chip_col="status",
                             chip_tone={"landed": "positive", "gap": "high"}))
    assert "bg-positive-tint" in html   # landed -> positive
    # gap -> high, and the unmapped 'other' value also falls back to high
    assert "bg-high-tint" in html
