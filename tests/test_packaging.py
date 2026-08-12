"""Contract tests for the Azure/Docker packaging (see Dockerfile, deploy/).

These run in the normal suite (no Docker needed) so drift between the repo and
what the image build assumes fails fast and locally, not on a cloud build.
"""

import importlib
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO / "Dockerfile"


def _dockerfile_text() -> str:
    assert DOCKERFILE.exists(), "Dockerfile missing — Azure packaging cannot build"
    return DOCKERFILE.read_text(encoding="utf-8")


def test_seed_inputs_present():
    # The Dockerfile bakes the demo DB from these; missing any breaks the build.
    for rel in (
        "sample_data/seed_snapshots.py",
        "sample_data/energy_pipeline_sample.csv",
        "sample_data/account_facts_sample.csv",
        "deploy/seed_account_facts.py",
    ):
        assert (REPO / rel).exists(), f"seed input {rel} referenced by the build is missing"


def test_runtime_config_present():
    # The app reads these YAMLs at call time; a missing one degrades a tool
    # silently rather than failing loudly.
    for rel in (
        "config/stage_map.yaml",
        "config/aliases.yaml",
        "config/risk_rules.yaml",
        "config/narrative_templates.yaml",
        "config/obligation_map.yaml",
        "config/product_map.yaml",
    ):
        assert (REPO / rel).exists(), f"config {rel} the app reads at runtime is missing"


def test_container_entrypoint_present():
    assert (REPO / "web" / "server.py").exists(), "FastHTML entrypoint moved — update Dockerfile CMD"
    assert (REPO / "app" / "Home.py").exists(), "Home entrypoint moved — update README quickstart"


def test_dockerfile_starts_fasthtml_tools():
    text = _dockerfile_text()
    assert "uvicorn web.server:app" in text
    assert "SELLER_ADMIN_TOOLS_ALLOW_REMOTE=1" in text


def test_dockerfile_and_deploy_agree_on_port():
    port = re.search(r"ENV PORT=(\d+)", _dockerfile_text())
    assert port, "Dockerfile no longer sets ENV PORT"
    deploy = (REPO / "deploy" / "azure-deploy.ps1").read_text(encoding="utf-8")
    assert re.search(rf"\$Port\s*=\s*{port.group(1)}\b", deploy), (
        f"deploy/azure-deploy.ps1 $Port must equal Dockerfile PORT ({port.group(1)})"
    )


def test_deploy_enables_acr_arm_auth_for_managed_identity_pull():
    deploy = (REPO / "deploy" / "azure-deploy.ps1").read_text(encoding="utf-8")
    assert re.search(
        r"az\s+acr\s+config\s+authentication-as-arm\s+update\b[^\r\n]*--status\s+enabled\b",
        deploy,
    ), "App Service managed-identity ACR pulls require ARM audience token auth"


def test_packaging_modules_importable():
    for mod in ("core.importer", "core.store", "core.mapping", "core.schema"):
        importlib.import_module(mod)
