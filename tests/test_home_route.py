"""Home route tests. The routes read/write the default db (snapshots + mapping
profiles), so every test isolates store.DEFAULT_DB to a tmp copy (no real
data/agents.db is touched). TestClient uses a 127.0.0.1 base_url + same-origin
Origin header so state-changing POSTs clear LocalOnlyMiddleware (its default
`testserver` host/origin would 403).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from core import ingest, store
from core.views import home as vm
from web.routes import home as route
from web.server import app

LOCAL = "http://127.0.0.1:8000"
BASE = "/home"
REPO = Path(__file__).resolve().parent.parent
PIPELINE_CSV = REPO / "sample_data" / "energy_pipeline_sample.csv"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DEFAULT_DB", tmp_path / "agents.db")
    route._UPLOADS.clear()
    return tmp_path


@pytest.fixture
def client():
    return TestClient(app, base_url=LOCAL, headers={"Origin": LOCAL})


def _upload(client):
    raw = PIPELINE_CSV.read_bytes()
    r = client.post(f"{BASE}/upload",
                    files={"pipeline_csv": ("pipeline.csv", raw, "text/csv")})
    token = re.search(r'name="token" value="([0-9a-f]+)"', r.text).group(1)
    return r, token, raw


def _confirm_data(token, raw, **overrides):
    m = vm.suggest_pipeline_mapping(list(ingest.load_csv(raw).columns))
    data = {"token": token, "date_format": "auto", "profile": vm.NEW_MAPPING,
            "label": "wk32", "save_as": "", "as_of": "2026-08-11"}
    for field, col in m.items():
        data[f"map_{field}"] = col or ""
    for raw_stage, bucket in {"04 Commit": "late", "03 Propose": "mid",
                              "02 Develop": "mid", "01 Qualify": "early"}.items():
        data[f"sb:{raw_stage}"] = bucket
    data.update(overrides)
    return data


def test_blocking_lines_carry_blocked_marker():
    # blocker vs warning must be distinguishable by a literal word, not hue alone
    from fasthtml.common import to_xml
    err = to_xml(route._validation_block(
        {"error": "Every slash-form date is ambiguous.", "blocking": [], "warnings": []}))
    assert ">Blocked</span>" in err
    blk = to_xml(route._validation_block(
        {"error": None, "blocking": ["Amount column not mapped."], "warnings": []}))
    assert ">Blocked</span>" in blk
    # warnings-only path stays a details/summary — no Blocked marker
    warn = to_xml(route._validation_block(
        {"error": None, "blocking": [], "warnings": ["3 rows lack opportunity_id"]}))
    assert ">Blocked</span>" not in warn


def test_page_renders_upload_panel(env, client):
    r = client.get(BASE)
    assert r.status_code == 200
    assert "Pipeline import" in r.text  # H1 (& is HTML-escaped in output)
    assert vm.UPLOAD_HINT in r.text
    assert 'name="pipeline_csv"' in r.text


def test_upload_returns_mapping_grid(env, client):
    r, token, _ = _upload(client)
    assert r.status_code == 200
    assert 'name="map_account_name"' in r.text
    assert "Stage buckets" in r.text
    assert "Confirm import" in r.text
    assert 'name="sb:Deal Review"' in r.text  # off-map stage surfaced
    assert len(route._UPLOADS) == 1


def test_preview_reacts_to_unmapping_required(env, client):
    _, token, raw = _upload(client)
    data = _confirm_data(token, raw)
    data["map_amount"] = ""  # unmap a required field
    r = client.post(f"{BASE}/preview", data=data)
    assert r.status_code == 200
    assert vm.REQUIRED_NOT_MAPPED in r.text
    # Confirm button disabled when blocked
    assert re.search(r"Confirm import</button>", r.text)
    assert "disabled" in r.text


def test_import_writes_snapshot(env, client):
    _, token, raw = _upload(client)
    r = client.post(f"{BASE}/import", data=_confirm_data(token, raw))
    assert r.status_code == 200
    assert "Imported snapshot 'wk32'" in r.text
    snaps = store.list_snapshots()
    assert len(snaps) == 1 and snaps.iloc[0]["label"] == "wk32"
    assert token not in route._UPLOADS  # consumed on success


def test_import_saves_profile(env, client):
    _, token, raw = _upload(client)
    client.post(f"{BASE}/import", data=_confirm_data(token, raw, save_as="Weekly"))
    profiles = route.mapping.load_profiles()
    assert "Weekly" in profiles
    assert profiles["Weekly"]["stage_assignments"]["04 Commit"] == "late"


def test_reserved_profile_name_not_saved(env, client):
    _, token, raw = _upload(client)
    r = client.post(f"{BASE}/import",
                    data=_confirm_data(token, raw, save_as=vm.NEW_MAPPING))
    assert vm.RESERVED_NAME_WARNING in r.text
    assert route.mapping.load_profiles() == {}


def test_duplicate_import_offers_override(env, client):
    _, token, raw = _upload(client)
    client.post(f"{BASE}/import", data=_confirm_data(token, raw))
    # re-upload the same bytes and import again -> duplicate guard
    _, token2, raw2 = _upload(client)
    r = client.post(f"{BASE}/import", data=_confirm_data(token2, raw2))
    assert "Already imported as 'wk32'" in r.text
    assert "Import anyway" in r.text
    assert len(store.list_snapshots()) == 1  # not yet duplicated

    over = client.post(f"{BASE}/import", data=_confirm_data(token2, raw2, override="1"))
    assert "Imported snapshot 'wk32'" in over.text
    assert len(store.list_snapshots()) == 2


def test_import_without_label_blocks(env, client):
    _, token, raw = _upload(client)
    r = client.post(f"{BASE}/import", data=_confirm_data(token, raw, label=""))
    assert "Enter a snapshot label to import." in r.text
    assert len(store.list_snapshots()) == 0


def test_reprofile_loads_saved_mapping(env, client):
    _, token, raw = _upload(client)
    client.post(f"{BASE}/import", data=_confirm_data(token, raw, save_as="Weekly"))
    _, token2, _ = _upload(client)
    r = client.post(f"{BASE}/reprofile", data={"token": token2, "profile": "Weekly"})
    assert r.status_code == 200
    assert 'name="map_account_name"' in r.text
    # save_as prefilled to the profile name on reprofile
    assert 'name="save_as" value="Weekly"' in r.text


def test_reprofile_without_upload_hints(env, client):
    r = client.post(f"{BASE}/reprofile", data={"token": "", "profile": vm.NEW_MAPPING})
    assert r.status_code == 200
    assert vm.UPLOAD_HINT in r.text


def test_bad_csv_shows_error(env, client):
    r = client.post(f"{BASE}/upload",
                    files={"pipeline_csv": ("empty.csv", b"", "text/csv")})
    assert r.status_code == 200
    assert "empty" in r.text.lower()
