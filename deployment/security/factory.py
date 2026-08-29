"""Construct target-specific security persistence services from deployment configuration.

The factory keeps OCI identifiers and authentication choices outside application lifecycle logic.
Local deployments deliberately return ``None`` because they retain the existing plaintext durable
security behavior.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from deployment.targets import DeploymentTarget
from deployment.topology import AgentNebulaDeploymentTopology

from .persistence import OciSecurityPersistenceService
from .vault import OciVaultConfiguration, OciVaultSecretClient


def build_security_persistence_service(
    *,
    target: DeploymentTarget,
    topology: AgentNebulaDeploymentTopology,
    environment: Mapping[str, str] | None = None,
) -> OciSecurityPersistenceService | None:
    """Return OCI encrypted persistence for OCI targets and no adapter for local targets."""

    if target is DeploymentTarget.LOCAL:
        return None
    # OCI Vault identifiers/authentication belong to the installer process environment.
    # Product environment files intentionally contain only application/runtime settings, so
    # overlay them on top of the process environment rather than replacing it.
    values = dict(os.environ)
    if environment is not None:
        values.update(environment)
    configuration = OciVaultConfiguration(
        compartment_ocid=values.get("ANU_OCI_COMPARTMENT_OCID", ""),
        vault_ocid=values.get("ANU_OCI_VAULT_OCID", ""),
        key_ocid=values.get("ANU_OCI_VAULT_KEY_OCID", ""),
        auth_mode=values.get("ANU_OCI_AUTH_MODE", "instance_principal"),
        secret_prefix=values.get("ANU_OCI_SECRET_PREFIX", "anu"),
    )
    staging_root = Path(
        values.get("DEPLOY_SECURITY_STAGING_ROOT", "/run/agent-nebula-security-staging")
    )
    return OciSecurityPersistenceService(
        topology=topology,
        vault=OciVaultSecretClient(configuration),
        staging_root=staging_root,
    )
