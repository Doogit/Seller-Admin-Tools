"""Freeze QBR goldens from CORE (core.deck) + the view model, per scenario in an
isolated db. Re-baseline tool: run only on an intentional core change.

    python tests/goldens/qbr/capture.py

Per scenario (sample/prior/empty):
    <key>.qbr.md    -> deck.build_md(...)                     (byte-identical target)
    <key>.pptx.json -> extract_pptx(deck.build_pptx(...))     (parsed content; date normalized)
    <key>.view.json -> qbr view model data fields             (metrics/stage/sub_vertical/top/risk)
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

import qbr_fixtures as qfx  # noqa: E402
from core import deck  # noqa: E402
from core.views import qbr as vm  # noqa: E402


def view_struct(v) -> dict:
    return {"metrics": v.metrics, "stage": v.stage, "sub_vertical": v.sub_vertical,
            "top": v.top, "risk": v.risk}


def main() -> None:
    for key, builder in qfx.BUILDERS.items():
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / "capture.db"
            sc = builder(db)
            md = deck.build_md(sc.current_id, sc.prior_id, sc.meta, db_path=db)
            prs = Presentation(deck.build_pptx(sc.current_id, sc.prior_id, sc.meta, db_path=db))
            pptx = qfx.extract_pptx(prs)
            v = vm.build(sc.current_id, sc.prior_id, sc.period, sc.team, sc.quota, db_path=db)

            (HERE / f"{key}.qbr.md").write_text(md, encoding="utf-8", newline="\n")
            (HERE / f"{key}.pptx.json").write_text(
                json.dumps(pptx, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8", newline="\n")
            (HERE / f"{key}.view.json").write_text(
                json.dumps(view_struct(v), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8", newline="\n")
            print(f"froze {key}: md={len(md)}B, slides={len(pptx['slides'])}, "
                  f"charts={len(pptx['charts'])}")


if __name__ == "__main__":
    main()
