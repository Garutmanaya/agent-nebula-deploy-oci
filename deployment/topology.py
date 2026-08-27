"""Canonical durable/runtime component placement for local and OCI deployments.

This module intentionally contains only product topology. Directory schema, initialization, and
runtime filesystem behavior are delegated to ``agent-nebula-utils`` so this repository does not
fork generic Agent Nebula deployment functionality.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_nebula_utils import DeploymentDirectory, anu_deployment_directory, anu_load_settings
from agent_nebula_utils.environment import AgentNebulaSettings


@dataclass(frozen=True, slots=True)
class DatabaseCredentialPaths:
    """Resolve database-password locations owned independently by each consumer.

    The database owns the canonical service credential. Core and OAuth receive their own durable
    credential copies during initialization so neither service reaches into another component's
    filesystem tree. Runtime materialization is handled separately by container startup.
    """

    database: DeploymentDirectory
    core: DeploymentDirectory
    oauth: DeploymentDirectory

    @property
    def source(self) -> Path:
        """Return the database-owned canonical service-password source path."""

        return self.database.secrets / "service-password"

    @property
    def core_destination(self) -> Path:
        """Return the Core-owned durable database-password path."""

        return self.core.secrets / "database" / "service-password"

    @property
    def oauth_destination(self) -> Path:
        """Return the OAuth-owned durable database-password path."""

        return self.oauth.secrets / "database" / "service-password"


@dataclass(frozen=True, slots=True)
class AgentNebulaDeploymentTopology:
    """Resolve the corrected Agent Nebula component ownership hierarchy.

    Core and Console remain grouped under the ``nebula`` product directory. Database, Explorer,
    OAuth, Policy, and Playground are standalone top-level products. Runtime roots mirror durable
    placement beneath ``ANU_RUNTIME_HOME``. The topology is target-neutral and therefore applies
    unchanged to both local laptop and OCI VM deployments.
    """

    settings: AgentNebulaSettings

    @classmethod
    def from_environment(
        cls,
        environment: dict[str, str] | None = None,
    ) -> AgentNebulaDeploymentTopology:
        """Create topology from canonical Utils settings and optional environment overrides."""

        return cls(settings=anu_load_settings(environment))

    def _directory(self, *parts: str) -> DeploymentDirectory:
        """Create one Utils-backed durable/runtime directory from matching relative parts."""

        relative = Path(*parts)
        return anu_deployment_directory(
            product_root=self.settings.home / relative,
            runtime_root=self.settings.runtime_home / relative,
            settings=self.settings,
        )

    @property
    def core(self) -> DeploymentDirectory:
        """Return the Core directory grouped beneath the Nebula platform root."""

        return self._directory(self.settings.nebula_dir, "core")

    @property
    def console(self) -> DeploymentDirectory:
        """Return the Console directory grouped beneath the Nebula platform root."""

        return self._directory(self.settings.nebula_dir, "console")

    @property
    def database(self) -> DeploymentDirectory:
        """Return the standalone PostgreSQL deployment directory."""

        return self._directory("database")

    @property
    def explorer(self) -> DeploymentDirectory:
        """Return the standalone Capability Explorer deployment directory."""

        return self._directory("explorer")

    @property
    def oauth(self) -> DeploymentDirectory:
        """Return the standalone OAuth Authorization Server deployment directory."""

        return self._directory("oauth")

    @property
    def policy(self) -> DeploymentDirectory:
        """Return the standalone Policy service deployment directory."""

        return self._directory("policy")

    def playground_component(self, name: str) -> DeploymentDirectory:
        """Return one Playground service directory beneath the standalone Playground product."""

        if not name or "/" in name or name in {".", ".."}:
            raise ValueError(f"Invalid Playground component name: {name!r}")
        return self._directory("playground", name)

    @property
    def playground_container(self) -> DeploymentDirectory:
        """Return the Playground experiment-container service directory."""

        return self.playground_component("container")

    @property
    def playground_backend(self) -> DeploymentDirectory:
        """Return the Playground backend service directory."""

        return self.playground_component("backend")

    @property
    def playground_ui(self) -> DeploymentDirectory:
        """Return the Playground UI service directory."""

        return self.playground_component("ui")

    @property
    def database_credentials(self) -> DatabaseCredentialPaths:
        """Return database credential paths with explicit component ownership."""

        return DatabaseCredentialPaths(
            database=self.database,
            core=self.core,
            oauth=self.oauth,
        )
