"""Phase 3 regression tests for deployment/environment ownership boundaries."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from agent_nebula_utils.environment.definitions import (
    ConsoleEnvironment,
    CoreEnvironment,
    ExplorerEnvironment,
    OAuthEnvironment,
    PolicyEnvironment,
)
from deploy.environment import DeploymentEnvironmentService
from deploy.lifecycle import HostDeploymentService
from deployment.targets import DeploymentTarget


@pytest.fixture
def environment_root() -> dict[str, str]:
    """Return deterministic host roots and hostname for environment composition tests."""

    return {
        "ANU_HOME": "/tmp/agent-nebula-test/opt",
        "ANU_RUNTIME_HOME": "/tmp/agent-nebula-test/run",
        "ANU_DEPLOY_LOCAL_HOSTNAME": "agentnebula-vnic",
    }


def _generate(environment: dict[str, str], target: DeploymentTarget, profile: str, product: str):
    return DeploymentEnvironmentService(environment, target=target).generate(
        product=product,
        profile=profile,
    ).values


def test_deploy_oci_supports_only_platform_products_and_host_profiles(environment_root) -> None:
    """CloudRun and Studio are not deployment products/profiles owned by deploy-OCI."""

    service = DeploymentEnvironmentService(environment_root)
    with pytest.raises(ValueError, match="Unsupported deployment profile"):
        service.generate(product="nebula", profile="cloudrun")
    with pytest.raises(ValueError, match="Unsupported deployment product"):
        service.generate(product="studio", profile="local")


def test_cloudflare_changes_only_public_console_registry_oauth_identities(environment_root) -> None:
    """Explorer, Playground, Policy, and OAuth service routing remain host-internal."""

    nebula = _generate(environment_root, DeploymentTarget.LOCAL, "cloudflare", "nebula")
    oauth = _generate(environment_root, DeploymentTarget.LOCAL, "cloudflare", "oauth")

    assert nebula[CoreEnvironment.PUBLIC_UI_URL.name] == "https://agentnebula.ai"
    assert nebula[CoreEnvironment.PUBLIC_API_URL.name] == "https://registry.agentnebula.ai"
    assert nebula[ConsoleEnvironment.API_URL.name] == "https://registry.agentnebula.ai"
    assert nebula[OAuthEnvironment.PUBLIC_URL.name] == "https://oauth.agentnebula.ai"
    assert nebula[OAuthEnvironment.SERVICE_URL.name] == "https://agentnebula-vnic:8092"
    assert nebula[ExplorerEnvironment.PUBLIC_URL.name] == "https://agentnebula-vnic:8001"
    assert nebula[ConsoleEnvironment.EXPLORER_URL.name] == "https://agentnebula-vnic:8001"
    assert nebula[ConsoleEnvironment.PLAYGROUND_URL.name] == "http://agentnebula-vnic:8094"
    assert nebula[PolicyEnvironment.SERVICE_URL.name] == "https://agentnebula-vnic:8093"
    assert oauth[OAuthEnvironment.PUBLIC_URL.name] == "https://oauth.agentnebula.ai"
    assert oauth[OAuthEnvironment.SERVICE_URL.name] == "https://agentnebula-vnic:8092"
    assert oauth[OAuthEnvironment.ISSUER.name] == "https://oauth.agentnebula.ai"
    assert oauth["ANU_NEBULA_URL"] == "https://agentnebula-vnic:8000"
    assert nebula["ANU_RUNTIME_MODE"] == "local"
    assert oauth["ANU_RUNTIME_MODE"] == "local"
    assert not any(name.startswith("ANU_DEPLOY_CLOUDFLARE_") for name in oauth)


def test_local_and_oci_application_values_differ_only_in_security_source(environment_root) -> None:
    """Deployment target changes host security staging, not application topology or URLs."""

    local = _generate(environment_root, DeploymentTarget.LOCAL, "local", "nebula")
    oci = _generate(environment_root, DeploymentTarget.OCI, "local", "nebula")
    differences = {name for name in local if local[name] != oci[name]}
    assert differences == {"DEPLOY_SECURITY_SOURCE_ROOT"}
    assert local["DEPLOY_SECURITY_SOURCE_ROOT"] == environment_root["ANU_HOME"]
    assert oci["DEPLOY_SECURITY_SOURCE_ROOT"] == "/run/agent-nebula-security-staging"


def test_component_init_reuses_existing_product_environment() -> None:
    """Component initialization must not regenerate and overwrite product-level environment."""

    existing = Mock(values={"ANU_HOME": "/tmp/nebula"})
    environments = Mock()
    environments.generate.return_value = existing
    service = object.__new__(HostDeploymentService)
    service._environments = environments
    service._target = DeploymentTarget.LOCAL

    bootstrap = Mock()
    bootstrap.initialize.return_value = True
    topology = Mock()
    with (
        patch("deploy.lifecycle.AgentNebulaDeploymentTopology.from_environment", return_value=topology),
        patch("deploy.lifecycle.build_security_persistence_service", return_value=None),
        patch("deploy.lifecycle.NebulaBootstrapService", return_value=bootstrap),
    ):
        assert service._initialize(
            product="nebula",
            profile="local",
            component="explorer",
            force_scope=None,
        )

    environments.generate.assert_called_once_with(
        product="nebula",
        profile="local",
        preserve_existing=True,
    )
    bootstrap.initialize.assert_called_once()


def test_cloudflare_template_exposes_only_console_registry_and_oauth() -> None:
    """Tunnel configuration must not expose Explorer or Playground directly."""

    template = (
        Path(__file__).resolve().parents[1]
        / "cloud"
        / "cloudflare"
        / "templates"
        / "config.yml.template"
    ).read_text(encoding="utf-8")
    assert "@PUBLIC_UI_HOST@" in template
    assert "@PUBLIC_API_HOST@" in template
    assert "@PUBLIC_OAUTH_HOST@" in template
    assert "EXPLORER" not in template
    assert "PLAYGROUND" not in template


def test_generated_environment_contains_no_undefined_agent_nebula_names() -> None:
    """Every concrete ANU token consumed by deploy-OCI must be canonical in Utils."""

    import re
    from agent_nebula_utils.environment import ALL_ENVIRONMENT_VARIABLES

    known = {definition.name for definition in ALL_ENVIRONMENT_VARIABLES}
    root = Path(__file__).resolve().parents[1]
    pattern = re.compile(r"ANU_[A-Z0-9_]+")
    undefined: dict[str, list[str]] = {}
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        for name in set(pattern.findall(path.read_text(encoding="utf-8", errors="ignore"))):
            # Prefix examples such as ANU_DEPLOY_CLOUDFLARE_ are documentation patterns,
            # not concrete environment-variable names.
            if name not in known and not name.endswith("_"):
                undefined.setdefault(name, []).append(str(path.relative_to(root)))
    assert undefined == {}


def test_deploy_oci_production_code_has_no_cloudrun_or_studio_behavior() -> None:
    """The Local/OCI deployment implementation cannot regain client/CloudRun behavior."""

    import re

    root = Path(__file__).resolve().parents[1]
    forbidden = re.compile(r"\bcloudrun\b|CloudRun|Cloud Run|CLOUDRUN|\bstudio\b|Studio|STUDIO")
    matches: list[str] = []
    for directory in (root / "deploy", root / "deployment"):
        for path in directory.rglob("*"):
            if path.is_file() and forbidden.search(
                path.read_text(encoding="utf-8", errors="ignore")
            ):
                matches.append(str(path.relative_to(root)))
    assert matches == []
