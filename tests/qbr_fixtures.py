"""Shared QBR fixtures + pptx extraction/normalization, imported by both the
golden-capture and the parity/view tests so they exercise identical inputs.

Scenarios:
  sample — the frozen sample CSV imported as one snapshot (rich: sub-vertical
           mapped, 10+ deals, risk flags). No prior.
  prior  — a synthetic prior+current pair (reuses the forecast `full` fixture):
           exercises WoW arrows, the two-series pptx chart, and coverage. No
           sub-vertical -> the 'unavailable' path.
  empty  — a zero-row snapshot.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

import forecast_narrative_fixtures as fnfx
from core import importer, ingest, mapping

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_CSV = REPO_ROOT / "sample_data" / "energy_pipeline_sample.csv"

_DATE_LINE = re.compile(r"Generated \d{4}-\d{2}-\d{2} from local snapshot data")
DATE_PLACEHOLDER = "Generated <DATE> from local snapshot data"


def _stage_map() -> dict:
    return yaml.safe_load(
        (REPO_ROOT / "config" / "stage_map.yaml").read_text(encoding="utf-8"))["stages"]


def _alias_index() -> dict:
    return ingest.load_alias_index(REPO_ROOT / "config" / "aliases.yaml")


@dataclass(frozen=True)
class QScenario:
    key: str
    current_id: int
    prior_id: int | None
    period: str
    team: str
    quota: float | None

    @property
    def meta(self) -> dict:
        return {"period": self.period, "team": self.team, "quota": self.quota}


def build_sample(db_path) -> QScenario:
    headers = list(ingest.load_csv(SAMPLE_CSV).columns)
    m = mapping.suggest_mapping(headers)
    res = importer.import_snapshot(
        SAMPLE_CSV, m, "auto", _stage_map(), "wk32",
        as_of_date=dt.date(2026, 8, 11), db_path=db_path, alias_index=_alias_index())
    return QScenario("sample", res.snapshot_id, None, "wk32", "Energy Team", None)


def build_prior(db_path) -> QScenario:
    sc = fnfx.build_full(db_path)  # wk31 (prior) + wk32 (current), synthetic
    return QScenario("prior", sc.current_id, sc.prior_id, "wk32", "Energy", 5_000_000.0)


def build_empty(db_path) -> QScenario:
    sc = fnfx.build_empty(db_path)
    return QScenario("empty", sc.current_id, None, "", "Team", None)


BUILDERS = {"sample": build_sample, "prior": build_prior, "empty": build_empty}


# --- pptx parsed-content extraction (the test_deck.py approach) --------------

def _shape_texts(slide) -> list[str]:
    out = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            out.append(shape.text_frame.text)
        elif shape.has_table:
            for row in shape.table.rows:
                for cell in row.cells:
                    out.append(cell.text)
    return out


def extract_pptx(prs) -> dict:
    """Parsed content only (never raw bytes): per-slide text + chart series.
    The Generated-<date> subtitle is normalized so the date can't make the
    parity oracle flap (deck.py stays untouched)."""
    slides = []
    charts = []
    for slide in prs.slides:
        slides.append([_DATE_LINE.sub(DATE_PLACEHOLDER, t) for t in _shape_texts(slide)])
        for shape in slide.shapes:
            if getattr(shape, "has_chart", False):
                for plot in shape.chart.plots:
                    for s in plot.series:
                        charts.append([s.name, [round(float(v), 4) if v is not None else None
                                                for v in s.values]])
    return {"slides": slides, "charts": charts}
