"""Freeze Forecast Narrative goldens from the CORE functions (not the view
model, not the live Streamlit page). Re-baseline tool: run only on an
intentional core change.

    python tests/goldens/forecast_narrative/capture.py

Writes, per scenario (full/minimal/empty):
    <key>.draft.json     -> narrative.draft(...) dict
    <key>.narrative.md   -> narrative.assemble_markdown(draft, period)

The parity test (tests/test_forecast_narrative_parity.py) asserts the view
model reproduces these byte-for-byte. Inputs come from
tests/forecast_narrative_fixtures.py so goldens and assertions never drift.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(HERE.parents[1]))  # tests/ dir (matches pytest prepend mode)

from core import forecast, narrative  # noqa: E402
import forecast_narrative_fixtures as fx  # noqa: E402


def capture_one(sc: fx.Scenario, db_path) -> tuple[dict, str]:
    """Reproduce the page's core-call sequence exactly (see
    app/pages/1_Forecast_Narrative.py), with no edits applied."""
    rollup = forecast.bucket_rollup(sc.current_id, db_path=db_path)
    prior_rollup = (forecast.bucket_rollup(sc.prior_id, db_path=db_path)
                    if sc.prior_id else None)
    deltas = forecast.wow_delta(sc.current_id, sc.prior_id, db_path=db_path)
    flags = forecast.risk_flags(sc.current_id, db_path=db_path)
    sections = narrative.draft(rollup, deltas, flags, prior_rollup=prior_rollup,
                               quota=sc.quota or None)
    period = sc.current_label.split(" ")[0]
    md = narrative.assemble_markdown(sections, period=period)
    return sections, md


def main() -> None:
    # Each scenario gets its OWN db: sharing one db would leak sibling snapshots
    # (same as_of_date) into risk_flags' prior-chain walk and suppress
    # stalled/slipped flags. This matches how the parity/view tests isolate them
    # and how a real single-tenant snapshot history behaves.
    for key, builder in fx.BUILDERS.items():
        # ignore_cleanup_errors: on Windows SQLite may still hold the db file
        # when the context exits; the golden is already written by then.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "capture.db"
            sc = builder(db_path)
            sections, md = capture_one(sc, db_path)
            # newline="\n": keep goldens LF on disk so the byte-identical .md
            # parity compare matches the view model's LF output on every platform
            # (Windows text-mode write would otherwise emit CRLF). Paired with
            # `.gitattributes` -text so LF survives a fresh checkout.
            (HERE / f"{key}.draft.json").write_text(
                json.dumps(sections, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8", newline="\n",
            )
            (HERE / f"{key}.narrative.md").write_text(md, encoding="utf-8", newline="\n")
            print(f"froze {key}: {len(sections)} sections, {len(md)} md bytes")


if __name__ == "__main__":
    main()
