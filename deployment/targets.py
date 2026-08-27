"""Deployment-target definitions shared by local laptop and OCI host workflows."""

from __future__ import annotations

from enum import Enum


class DeploymentTarget(str, Enum):
    """Select the host/image model without changing Agent Nebula application behavior."""

    LOCAL = "local"
    OCI = "oci"

    @property
    def architecture(self) -> str:
        """Return the image architecture associated with this deployment target."""

        return "amd64" if self is DeploymentTarget.LOCAL else "arm64"

    @property
    def image_source(self) -> str:
        """Return the canonical Utils image-source value for this target."""

        return "registry"
