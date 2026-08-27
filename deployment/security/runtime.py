"""Host runtime preparation for security material needed before Compose starts.

Most Agent Nebula containers materialize their own security files. PostgreSQL remains a stock image,
so Deploy prepares only its required plaintext files under host ``/run`` and mounts those ephemeral
files into the database container.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_nebula_utils import (
    EncryptedFileSecurityMaterializationStrategy,
    PlainFileSecurityMaterializationStrategy,
    RuntimeSecurityMaterializer,
    SecurityMaterializationStrategy,
    anu_ca_paths,
    anu_initialize_runtime_directory,
)

from deployment.targets import DeploymentTarget
from deployment.topology import AgentNebulaDeploymentTopology


@dataclass(frozen=True, slots=True)
class HostRuntimeSecurityService:
    """Prepare target-neutral host runtime files required by stock infrastructure containers."""

    topology: AgentNebulaDeploymentTopology
    target: DeploymentTarget
    masker_key_file: Path

    def prepare(self) -> None:
        """Prepare shared host runtime trust plus PostgreSQL security material."""

        self.prepare_platform_ca()
        self.prepare_database()
        self.prepare_non_python_tls()

    def prepare_platform_ca(self) -> Path:
        """Materialize the shared root CA certificate for host-side health and trust operations."""

        strategy = self._strategy()
        ca = anu_ca_paths(self.topology.settings)
        destination = self.topology.settings.runtime_home / "nebula-ca" / "pki" / "root-ca.crt"
        RuntimeSecurityMaterializer(strategy).materialize_file(
            source=ca.root_certificate, destination=destination, mode=0o644
        )
        return destination

    def prepare_non_python_tls(self) -> None:
        """Materialize TLS files for Node/static containers that do not import Agent Nebula Utils."""

        strategy = self._strategy()
        materializer = RuntimeSecurityMaterializer(strategy)
        for directory in (self.topology.console, self.topology.playground_ui):
            anu_initialize_runtime_directory(directory)
            if directory.certs.exists():
                materializer.materialize(directory)

    def prepare_database(self) -> None:
        """Materialize PostgreSQL password/TLS files into ephemeral host runtime storage."""

        database = anu_initialize_runtime_directory(self.topology.database)
        strategy = self._strategy()
        materializer = RuntimeSecurityMaterializer(strategy)
        materializer.materialize(database)
        ca = anu_ca_paths(self.topology.settings)
        materializer.materialize_file(
            source=ca.root_certificate,
            destination=database.runtime_pki / "root-ca.crt",
            mode=0o644,
        )

    def _strategy(self) -> SecurityMaterializationStrategy:
        """Return the target-specific shared Utils materialization strategy."""

        if self.target is DeploymentTarget.LOCAL:
            return PlainFileSecurityMaterializationStrategy()
        return EncryptedFileSecurityMaterializationStrategy(masker_key_file=self.masker_key_file)
