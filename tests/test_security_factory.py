"""Tests for target-specific security persistence configuration."""

from pathlib import Path

from agent_nebula_utils import anu_load_settings

from deployment.security.factory import build_security_persistence_service
from deployment.targets import DeploymentTarget
from deployment.topology import AgentNebulaDeploymentTopology


def test_oci_factory_keeps_process_vault_configuration_with_product_environment(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Generated product env must not hide installer-owned OCI Vault configuration."""

    monkeypatch.setenv("ANU_OCI_COMPARTMENT_OCID", "ocid1.tenancy.test")
    monkeypatch.setenv("ANU_OCI_VAULT_OCID", "ocid1.vault.test")
    monkeypatch.setenv("ANU_OCI_VAULT_KEY_OCID", "ocid1.key.test")
    monkeypatch.setenv("ANU_OCI_AUTH_MODE", "instance_principal")

    home = tmp_path / "opt"
    staging = tmp_path / "staging"
    product_environment = {
        "ANU_HOME": str(home),
        "ANU_RUNTIME_HOME": str(tmp_path / "run"),
        "DEPLOY_SECURITY_STAGING_ROOT": str(staging),
    }
    topology = AgentNebulaDeploymentTopology(
        anu_load_settings(product_environment)
    )

    persistence = build_security_persistence_service(
        target=DeploymentTarget.OCI,
        topology=topology,
        environment=product_environment,
    )

    assert persistence is not None
    assert persistence.staging_root == staging
