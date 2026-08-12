"""QBR parity gate (Task 4): the view model + reused deck must reproduce the
goldens frozen from core.

- .md export: BYTE-identical vs the frozen .md (deck.build_md is deterministic).
- .pptx: PARSED-content compare (slide texts / table cells / chart series) with
  the Generated-<date> line normalized — never raw bytes, never editing deck.py.
- view struct == frozen view.json.

Each scenario is built in its own db. Never edit a golden to pass — re-baseline
via tests/goldens/qbr/capture.py on an intentional core change.
"""

import json
from pathlib import Path

import pytest
from pptx import Presentation

import qbr_fixtures as qfx

from core import deck
from core.views import qbr as vm

GOLDEN_DIR = Path(__file__).resolve().parent / "goldens" / "qbr"
ALLOWLIST: dict[str, str] = {}  # must stay empty


@pytest.mark.parametrize("key", list(qfx.BUILDERS))
def test_md_byte_identical(key, tmp_path):
    if key in ALLOWLIST:
        pytest.skip(ALLOWLIST[key])
    sc = qfx.BUILDERS[key](tmp_path / f"{key}.db")
    md = deck.build_md(sc.current_id, sc.prior_id, sc.meta, db_path=tmp_path / f"{key}.db")
    golden = (GOLDEN_DIR / f"{key}.qbr.md").read_bytes()
    assert md.encode("utf-8") == golden, f"{key}: .md drifted from golden"


@pytest.mark.parametrize("key", list(qfx.BUILDERS))
def test_pptx_parsed_content_matches(key, tmp_path):
    if key in ALLOWLIST:
        pytest.skip(ALLOWLIST[key])
    db = tmp_path / f"{key}.db"
    sc = qfx.BUILDERS[key](db)
    prs = Presentation(deck.build_pptx(sc.current_id, sc.prior_id, sc.meta, db_path=db))
    got = qfx.extract_pptx(prs)
    golden = json.loads((GOLDEN_DIR / f"{key}.pptx.json").read_text(encoding="utf-8"))
    assert got == golden, f"{key}: .pptx parsed content drifted from golden"


@pytest.mark.parametrize("key", list(qfx.BUILDERS))
def test_view_struct_matches(key, tmp_path):
    if key in ALLOWLIST:
        pytest.skip(ALLOWLIST[key])
    db = tmp_path / f"{key}.db"
    sc = qfx.BUILDERS[key](db)
    v = vm.build(sc.current_id, sc.prior_id, sc.period, sc.team, sc.quota, db_path=db)
    got = {"metrics": v.metrics, "stage": v.stage, "sub_vertical": v.sub_vertical,
           "top": v.top, "risk": v.risk}
    golden = json.loads((GOLDEN_DIR / f"{key}.view.json").read_text(encoding="utf-8"))
    assert got == golden, f"{key}: view struct drifted from golden"
