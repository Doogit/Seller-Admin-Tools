"""Shared Account-Plan fixtures, imported by both the golden-capture and the
parity/view tests so they exercise identical inputs.

Every scenario seeds the frozen account-facts sample through the real importer
(mapping via suggest_mapping + ACCOUNT_SCHEMA) into an isolated db; the pipeline
scenarios also import the frozen pipeline sample as one snapshot. Account names
are resolved from the seeded facts by their raw spelling, so the fixture is
robust to normalization/aliasing.

Scenarios:
  full        — Meridian Energy + pipeline: install_base + incumbents produce a
                landed/partial/gap mix, open pipeline drives whitespace.
  no_pipeline — Meridian Energy, snapshot_id=None: plan renders without pipeline.
  minimal     — Cascade Power & Light + pipeline: empty footprint -> all gaps.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import yaml

from core import importer, ingest, mapping, schema, store

REPO_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_CSV = REPO_ROOT / "sample_data" / "energy_pipeline_sample.csv"
FACTS_CSV = REPO_ROOT / "sample_data" / "account_facts_sample.csv"


def _stage_map() -> dict:
    return yaml.safe_load(
        (REPO_ROOT / "config" / "stage_map.yaml").read_text(encoding="utf-8"))["stages"]


def _alias_index() -> dict:
    return ingest.load_alias_index(REPO_ROOT / "config" / "aliases.yaml")


@dataclass(frozen=True)
class AScenario:
    key: str
    account_name: str
    snapshot_id: int | None


def _seed_facts(db_path) -> None:
    headers = list(ingest.load_csv(FACTS_CSV.read_bytes()).columns)
    m = mapping.suggest_mapping(headers, schema.ACCOUNT_SCHEMA)
    importer.import_account_facts(
        FACTS_CSV.read_bytes(), m, "auto", alias_index=_alias_index(), db_path=db_path)


def _seed_pipeline(db_path) -> int:
    headers = list(ingest.load_csv(PIPELINE_CSV).columns)
    m = mapping.suggest_mapping(headers)
    res = importer.import_snapshot(
        PIPELINE_CSV, m, "auto", _stage_map(), "wk32",
        as_of_date=dt.date(2026, 8, 11), db_path=db_path, alias_index=_alias_index())
    return res.snapshot_id


def _account_by_raw(db_path, raw: str) -> str:
    facts = store.load_account_facts(db_path=db_path)
    return facts.loc[facts["account_name_raw"] == raw, "account_name"].iloc[0]


def build_full(db_path) -> AScenario:
    _seed_facts(db_path)
    sid = _seed_pipeline(db_path)
    return AScenario("full", _account_by_raw(db_path, "Meridian Energy"), sid)


def build_no_pipeline(db_path) -> AScenario:
    _seed_facts(db_path)
    return AScenario("no_pipeline", _account_by_raw(db_path, "Meridian Energy"), None)


def build_minimal(db_path) -> AScenario:
    _seed_facts(db_path)
    sid = _seed_pipeline(db_path)
    return AScenario("minimal", _account_by_raw(db_path, "Cascade Power & Light"), sid)


BUILDERS = {"full": build_full, "no_pipeline": build_no_pipeline, "minimal": build_minimal}


# --- pptx parsed-content extraction (the test_deck.py approach) --------------
# plan.plan_pptx has no dated subtitle (deck.build_pptx's "Generated <date>" line
# is QBR-only), so there is nothing to normalize — a plain parsed compare.

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
    """Parsed content only (never raw bytes): per-slide text + table cells."""
    return {"slides": [_shape_texts(slide) for slide in prs.slides]}
