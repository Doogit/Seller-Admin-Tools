"""Account-Plan route tests. The routes read/write the default db and config, so
every test isolates store.DEFAULT_DB and the alias/product-map paths to tmp
copies (no real data/agents.db or config/*.yaml is touched). TestClient uses a
127.0.0.1 base_url so it keeps passing once the loopback/CSRF middleware lands
(its default `testserver` host would fail the Host guard).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import account_plan_fixtures as afx
from core import crosswalk, store
from web.routes import account_plan as route
from web.server import app

LOCAL = "http://127.0.0.1:8000"
BASE = "/account-plan"
REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "agents.db"
    monkeypatch.setattr(store, "DEFAULT_DB", db)
    aliases = tmp_path / "aliases.yaml"
    products = tmp_path / "product_map.yaml"
    shutil.copy(REPO / "config" / "aliases.yaml", aliases)
    shutil.copy(REPO / "config" / "product_map.yaml", products)
    monkeypatch.setattr(route, "ALIASES_PATH", aliases)
    monkeypatch.setattr(crosswalk, "DEFAULT_PRODUCTS", products)
    route._UPLOADS.clear()
    return {"db": db, "aliases": aliases, "products": products}


@pytest.fixture
def client():
    # loopback Host + same-origin Origin so POSTs clear LocalOnlyMiddleware
    # (its default TestClient host/origin would 403 on state-changing requests).
    return TestClient(app, base_url=LOCAL, headers={"Origin": LOCAL})


def _seed(db):
    afx._seed_facts(db)
    return afx._seed_pipeline(db)


def test_empty_state_without_facts(env, client):
    r = client.get(BASE)
    assert r.status_code == 200
    assert "Import an account-facts CSV to begin" in r.text
    assert 'id="plan"' not in r.text


def test_page_renders_plan_with_facts(env, client):
    _seed(env["db"])
    r = client.get(BASE)
    assert r.status_code == 200
    assert "Plan — " in r.text
    assert route.vm.METRIC_WHITESPACE in r.text
    assert "Obligation → capability → gap" in r.text


def test_upload_returns_mapping_grid(env, client):
    raw = afx.FACTS_CSV.read_bytes()
    r = client.post(f"{BASE}/facts/upload",
                    files={"facts_csv": ("facts.csv", raw, "text/csv")})
    assert r.status_code == 200
    assert 'name="map_account_name"' in r.text
    assert "Import account facts" in r.text
    assert len(route._UPLOADS) == 1  # stashed by token


def test_upload_then_import_seeds_facts(env, client):
    raw = afx.FACTS_CSV.read_bytes()
    up = client.post(f"{BASE}/facts/upload",
                     files={"facts_csv": ("facts.csv", raw, "text/csv")})
    token = re.search(r'name="token" value="([0-9a-f]+)"', up.text).group(1)
    suggested = route.vm.suggest_facts_mapping(
        list(route.ingest.load_csv(raw).columns))
    data = {"token": token, "date_format": "auto"}
    for field, col in suggested.items():
        data[f"map_{field}"] = col or ""
    imp = client.post(f"{BASE}/facts/import", data=data)
    assert imp.status_code == 200
    assert "Plan — " in imp.text
    assert not store.load_account_facts().empty  # written to the isolated db


def test_ambiguous_date_import_rerenders_grid_without_write(env, client):
    raw = (
        b"Account Name,Sub-Vertical,Agreement End\n"
        b"Acme Power,Power & Utilities,03/04/2026\n"
    )
    up = client.post(f"{BASE}/facts/upload",
                     files={"facts_csv": ("facts.csv", raw, "text/csv")})
    token = re.search(r'name="token" value="([0-9a-f]+)"', up.text).group(1)
    suggested = route.vm.suggest_facts_mapping(
        list(route.ingest.load_csv(raw).columns))
    data = {"token": token, "date_format": "auto"}
    for field, col in suggested.items():
        data[f"map_{field}"] = col or ""

    preview = client.post(f"{BASE}/facts/preview", data=data)
    assert route.vm.AMBIGUOUS_DATE_ERROR in preview.text
    assert "Import account facts</button>" in preview.text
    assert "disabled" in preview.text

    imp = client.post(f"{BASE}/facts/import", data=data)
    assert imp.status_code == 200
    assert route.vm.AMBIGUOUS_DATE_ERROR in imp.text
    assert "Traceback" not in imp.text
    assert store.load_account_facts().empty


def test_plan_fragment_for_selected_account(env, client):
    sid = _seed(env["db"])
    r = client.get(f"{BASE}/plan",
                   params={"account_name": "meridian energy", "snapshot_id": str(sid)})
    assert r.status_code == 200
    assert "Plan — Meridian Energy" in r.text
    assert 'id="plan"' in r.text


def test_gap_status_renders_toned_chips_not_emoji(env, client):
    # Meridian has a landed/partial/gap mix -> each status is a colorblind-safe
    # chip toned per GAP_TONES (positive/medium/high), never a color-only glyph.
    sid = _seed(env["db"])
    r = client.get(f"{BASE}/plan",
                   params={"account_name": "meridian energy", "snapshot_id": str(sid)})
    assert r.status_code == 200
    for glyph in ("🔴", "🟡", "🟢"):
        assert glyph not in r.text
    assert "bg-positive-tint" in r.text  # landed -> positive
    assert "bg-medium-tint" in r.text    # partial -> medium
    assert "bg-high-tint" in r.text      # gap -> high


def test_plan_fragment_resolves_stale_query_values(env, client):
    _seed(env["db"])
    r = client.get(f"{BASE}/plan",
                   params={"account_name": "missing", "snapshot_id": "999999"})
    assert r.status_code == 200
    assert 'id="plan"' in r.text
    assert "Traceback" not in r.text


def test_download_md_streams_plan(env, client):
    sid = _seed(env["db"])
    r = client.get(f"{BASE}/export/md",
                   params={"account_name": "meridian energy", "snapshot_id": str(sid)})
    assert r.status_code == 200
    assert r.text.startswith("# Account plan — Meridian Energy")
    assert "account_plan_meridian_energy_" in r.headers["content-disposition"]
    assert r.headers["content-disposition"].endswith('.md"')


def test_download_without_facts_returns_404(env, client):
    r = client.get(f"{BASE}/export/md",
                   params={"account_name": "missing", "snapshot_id": "999999"})
    assert r.status_code == 404
    assert r.text == "No account facts imported."


def test_download_pptx_streams_bytes(env, client):
    sid = _seed(env["db"])
    r = client.get(f"{BASE}/export/pptx",
                   params={"account_name": "meridian energy", "snapshot_id": str(sid)})
    assert r.status_code == 200
    assert r.content[:2] == b"PK"  # a .pptx is a zip
    assert r.headers["content-disposition"].endswith('.pptx"')


def test_product_assign_appends_alias(env, client):
    import yaml
    sid = _seed(env["db"])
    r = client.post(f"{BASE}/product",
                    data={"account_name": "meridian energy", "product": "Widget X",
                          "category": "siem", "snapshot_id": str(sid)})
    assert r.status_code == 200
    data = yaml.safe_load(env["products"].read_text(encoding="utf-8"))
    assert "widget x" in data["products"]["siem"]


def test_alias_confirm_rewrites_facts(env, client):
    import yaml
    sid = _seed(env["db"])
    # Gulf Stream Petroleum (facts) -> gulfstream petroleum (pipeline)
    r = client.post(f"{BASE}/alias",
                    data={"account_name": "gulf stream petroleum",
                          "pick": "gulfstream petroleum", "snapshot_id": str(sid)})
    assert r.status_code == 200
    names = store.load_account_facts()["account_name"].tolist()
    assert "gulfstream petroleum" in names
    assert "gulf stream petroleum" not in names
    data = yaml.safe_load(env["aliases"].read_text(encoding="utf-8"))
    assert "gulfstream petroleum" in data["accounts"]
