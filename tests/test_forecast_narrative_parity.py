"""Parity gate for tool 1 (Task 4): the view model must reproduce the goldens
frozen from the core functions at the branch base (tests/goldens/...), proving
the port broke nothing.

- draft sections: structural equality vs the frozen draft.json.
- .md export: BYTE-identical vs the frozen .md (deterministic — no masking).

Each scenario is built in its OWN db (matching capture.py) so risk history is
not polluted by sibling snapshots. Any intentional divergence would need an
ALLOWLIST entry with a justification; the allowlist is expected to stay empty.
Never edit a golden to make this pass — re-baseline only on an intentional core
change via tests/goldens/forecast_narrative/capture.py.
"""

import json
from pathlib import Path

import pytest

import forecast_narrative_fixtures as fx

from core.views import forecast_narrative as vm

GOLDEN_DIR = Path(__file__).resolve().parent / "goldens" / "forecast_narrative"

# {scenario_key: reason} — must stay empty for a clean port.
ALLOWLIST: dict[str, str] = {}


@pytest.mark.parametrize("key", list(fx.BUILDERS))
def test_draft_matches_golden(key, tmp_path):
    if key in ALLOWLIST:
        pytest.skip(f"allowlisted: {ALLOWLIST[key]}")
    sc = fx.BUILDERS[key](tmp_path / f"{key}.db")
    v = vm.build(sc.current_id, sc.prior_id, sc.quota, db_path=tmp_path / f"{key}.db")
    golden = json.loads((GOLDEN_DIR / f"{key}.draft.json").read_text(encoding="utf-8"))
    assert v.draft == golden


@pytest.mark.parametrize("key", list(fx.BUILDERS))
def test_md_export_byte_identical(key, tmp_path):
    if key in ALLOWLIST:
        pytest.skip(f"allowlisted: {ALLOWLIST[key]}")
    db = tmp_path / f"{key}.db"
    sc = fx.BUILDERS[key](db)
    v = vm.build(sc.current_id, sc.prior_id, sc.quota, db_path=db)
    produced = vm.export_markdown(v.draft, v.period).encode("utf-8")
    golden = (GOLDEN_DIR / f"{key}.narrative.md").read_bytes()
    assert produced == golden, f"{key}: .md export drifted from frozen golden"
