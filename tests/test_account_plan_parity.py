"""Account-Plan parity gate: the view model + reused core.plan must reproduce
the goldens frozen from core.

- .md export: BYTE-identical vs the frozen .md (plan.plan_md is deterministic).
- .pptx: PARSED-content compare (slide texts / table cells) — never raw bytes,
  never editing core.plan. plan.plan_pptx has no dated line, so nothing is
  normalized.
- view struct == frozen view.json.

Each scenario is built in its own db. Never edit a golden to pass — re-baseline
via tests/goldens/account_plan/capture.py on an intentional core change.
"""

import json
from pathlib import Path

import pytest
from pptx import Presentation

import account_plan_fixtures as afx

from core import plan
from core.views import account_plan as vm

GOLDEN_DIR = Path(__file__).resolve().parent / "goldens" / "account_plan"
ALLOWLIST: dict[str, str] = {}  # must stay empty


@pytest.mark.parametrize("key", list(afx.BUILDERS))
def test_md_byte_identical(key, tmp_path):
    if key in ALLOWLIST:
        pytest.skip(ALLOWLIST[key])
    db = tmp_path / f"{key}.db"
    sc = afx.BUILDERS[key](db)
    sections, disclaimer = vm.export_inputs(sc.account_name, sc.snapshot_id, db_path=db)
    md = plan.plan_md(sections, disclaimer)
    golden = (GOLDEN_DIR / f"{key}.plan.md").read_bytes()
    assert md.encode("utf-8") == golden, f"{key}: .md drifted from golden"


@pytest.mark.parametrize("key", list(afx.BUILDERS))
def test_pptx_parsed_content_matches(key, tmp_path):
    if key in ALLOWLIST:
        pytest.skip(ALLOWLIST[key])
    db = tmp_path / f"{key}.db"
    sc = afx.BUILDERS[key](db)
    sections, disclaimer = vm.export_inputs(sc.account_name, sc.snapshot_id, db_path=db)
    prs = Presentation(plan.plan_pptx(sections, disclaimer))
    got = afx.extract_pptx(prs)
    golden = json.loads((GOLDEN_DIR / f"{key}.pptx.json").read_text(encoding="utf-8"))
    assert got == golden, f"{key}: .pptx parsed content drifted from golden"


@pytest.mark.parametrize("key", list(afx.BUILDERS))
def test_view_struct_matches(key, tmp_path):
    if key in ALLOWLIST:
        pytest.skip(ALLOWLIST[key])
    db = tmp_path / f"{key}.db"
    sc = afx.BUILDERS[key](db)
    v = vm.build(sc.account_name, sc.snapshot_id, db_path=db)
    got = {"account_display": v.account_display, "summary": v.summary,
           "metrics": v.metrics, "unmeasurable": v.unmeasurable,
           "gaps": v.gaps, "uncovered": v.uncovered,
           "unresolved": v.unresolved, "pipeline": v.pipeline,
           "next_actions": v.next_actions, "relationship_map": v.relationship_map,
           "warnings": v.warnings, "zero_match": v.zero_match,
           "disclaimer": v.disclaimer, "safe_name": v.safe_name}
    golden = json.loads((GOLDEN_DIR / f"{key}.view.json").read_text(encoding="utf-8"))
    assert got == golden, f"{key}: view struct drifted from golden"
