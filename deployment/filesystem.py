"""Host-side durable filesystem initialization for Agent Nebula deployment targets.

Only durable component roots under ``ANU_HOME`` are created here. Container-owned runtime roots
under ``ANU_RUNTIME_HOME`` remain untouched, matching the existing Agent Nebula deployment
contract. Generic component directory creation is delegated to ``agent-nebula-utils``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_nebula_utils import DeploymentDirectory, anu_initialize_durable_directory

from .topology import AgentNebulaDeploymentTopology


@dataclass(frozen=True, slots=True)
class DeploymentFilesystemInitializer:
    """Initialize the corrected durable layout without deleting existing component state."""

    topology: AgentNebulaDeploymentTopology

    def directories(self) -> tuple[DeploymentDirectory, ...]:
        """Return all durable component directories managed by local and OCI deployment."""

        return (
            self.topology.core,
            self.topology.console,
            self.topology.database,
            self.topology.explorer,
            self.topology.oauth,
            self.topology.policy,
            self.topology.playground_container,
            self.topology.playground_backend,
            self.topology.playground_ui,
        )

    def initialize(self) -> tuple[DeploymentDirectory, ...]:
        """Create all durable component layouts and database credential ownership directories."""

        directories = self.directories()
        for directory in directories:
            anu_initialize_durable_directory(directory)

        self._initialize_database_credential_directories()
        return directories

    def _initialize_database_credential_directories(self) -> None:
        """Create private Core/OAuth credential subdirectories with restrictive permissions."""

        credentials = self.topology.database_credentials
        for destination in (
            credentials.core_destination.parent,
            credentials.oauth_destination.parent,
        ):
            self._ensure_private_directory(destination)

    @staticmethod
    def _ensure_private_directory(path: Path) -> None:
        """Create one credential directory idempotently while preserving an existing mode."""

        existed = path.exists()
        if existed and not path.is_dir():
            raise NotADirectoryError(f"Credential path exists but is not a directory: {path}")
        path.mkdir(parents=True, exist_ok=True)
        if not existed:
            path.chmod(0o700)
