"""Public deployment package API with lazy imports.

The image build pipeline imports lightweight modules from this package without installing the
runtime Agent Nebula Python dependencies.  Lazy public imports preserve the package API while
preventing build-only commands from loading filesystem/runtime dependencies unnecessarily.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .filesystem import DeploymentFilesystemInitializer
    from .topology import AgentNebulaDeploymentTopology, DatabaseCredentialPaths

__all__ = [
    "AgentNebulaDeploymentTopology",
    "DatabaseCredentialPaths",
    "DeploymentFilesystemInitializer",
]


def __getattr__(name: str) -> Any:
    """Load exported deployment objects only when callers explicitly request them."""
    if name == "DeploymentFilesystemInitializer":
        from .filesystem import DeploymentFilesystemInitializer

        return DeploymentFilesystemInitializer
    if name == "AgentNebulaDeploymentTopology":
        from .topology import AgentNebulaDeploymentTopology

        return AgentNebulaDeploymentTopology
    if name == "DatabaseCredentialPaths":
        from .topology import DatabaseCredentialPaths

        return DatabaseCredentialPaths
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
