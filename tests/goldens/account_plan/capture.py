"""Freeze Account-Plan goldens from CORE (core.plan) + the view model, per
scenario in an isolated db. Re-baseline tool: run only on an intentional core
change.

    python tests/goldens/account_plan/capture.py

Per scenario (full/no_pipeline/minimal):
    <key>.plan.md   -> plan.plan_md(sections, disclaimer)        (byte-identical target)
    <key>.pptx.json -> extract_pptx(plan.plan_pptx(...))         (parsed content; no date)
    <key>.view.json -> account-plan view model struct
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from pptx import Presentation

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(HERE.parents[1]))  # tests/ dir

import account_plan_fixtures as afx  # noqa: E402
from core import plan  # noqa: E402
from core.views import account_plan as vm  # noqa: E402


def view_struct(v) -> dict:
    return {"account_display": v.account_display, "summary": v.summary,
            "metrics": v.metrics, "gaps": v.gaps, "uncovered": v.uncovered,
            "unresolved": v.unresolved, "pipeline": v.pipeline,
            "next_actions": v.next_actions, "relationship_map": v.relationship_map,
            "warnings": v.warnings, "zero_match": v.zero_match,
            "disclaimer": v.disclaimer, "safe_name": v.safe_name}


def main() -> None:
    for key, builder in afx.BUILDERS.items():
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / "capture.db"
            sc = builder(db)
            sections, disclaimer = vm.export_inputs(sc.account_name, sc.snapshot_id, db_path=db)
            md = plan.plan_md(sections, disclaimer)
            prs = Presentation(plan.plan_pptx(sections, disclaimer))
            pptx = afx.extract_pptx(prs)
            v = vm.build(sc.account_name, sc.snapshot_id, db_path=db)

            (HERE / f"{key}.plan.md").write_text(md, encoding="utf-8", newline="\n")
            (HERE / f"{key}.pptx.json").write_text(
                json.dumps(pptx, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8", newline="\n")
            (HERE / f"{key}.view.json").write_text(
                json.dumps(view_struct(v), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8", newline="\n")
            print(f"froze {key}: md={len(md)}B, slides={len(pptx['slides'])}")


if __name__ == "__main__":
    main()
