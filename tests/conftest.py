import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import pytest
import yaml

from core import ingest, mapping

SAMPLE_CSV = REPO_ROOT / "sample_data" / "energy_pipeline_sample.csv"


@pytest.fixture
def sample_path() -> Path:
    return SAMPLE_CSV


@pytest.fixture
def db_path(tmp_path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def stage_map() -> dict:
    return yaml.safe_load(
        (REPO_ROOT / "config" / "stage_map.yaml").read_text(encoding="utf-8")
    )["stages"]


@pytest.fixture
def alias_index() -> dict:
    return ingest.load_alias_index(REPO_ROOT / "config" / "aliases.yaml")


@pytest.fixture
def sample_mapping() -> dict:
    headers = list(ingest.load_csv(SAMPLE_CSV).columns)
    return mapping.suggest_mapping(headers)


@pytest.fixture
def sample_snapshot(db_path, sample_mapping, stage_map, alias_index) -> int:
    import datetime as dt

    from core import importer

    result = importer.import_snapshot(
        SAMPLE_CSV, sample_mapping, "auto", stage_map, "wk32",
        as_of_date=dt.date(2026, 8, 11), db_path=db_path, alias_index=alias_index,
    )
    return result.snapshot_id
