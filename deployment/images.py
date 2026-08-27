"""Shared image manifest and registry models for build and deployment workflows.

Application repositories continue to own Dockerfiles. This module owns only the image metadata
needed by the OCI/local deployment repository so build, push, and runtime image resolution all use
one implementation and one configuration source.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ImageSpec:
    """Describe one buildable Agent Nebula image from ``config/images.json``."""

    name: str
    repository: str
    image: str
    dockerfile: str
    context: str = "."
    build_contexts: dict[str, str] = field(default_factory=dict)
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class RegistryConfig:
    """Describe the configured external container registry and release-tag templates."""

    provider: str
    host: str
    namespace: str
    project: str
    tag_templates: tuple[str, ...]


class ImageConfigurationRepository:
    """Load and validate image/registry configuration from repository-owned JSON files."""

    def __init__(self, manifest_path: Path, registry_path: Path) -> None:
        """Capture explicit configuration paths without relying on process working directory."""

        self._manifest_path = manifest_path.expanduser().resolve()
        self._registry_path = registry_path.expanduser().resolve()

    def load_manifest(self) -> tuple[dict[str, Any], list[ImageSpec]]:
        """Return manifest defaults and image specifications in declaration order."""

        payload = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            raise ValueError("Unsupported images manifest schema_version")
        specs = [
            ImageSpec(
                name=raw["name"],
                repository=raw["repository"],
                image=raw["image"],
                dockerfile=raw["dockerfile"],
                context=raw.get("context", "."),
                build_contexts=raw.get("build_contexts", {}),
                enabled=raw.get("enabled", True),
            )
            for raw in payload.get("images", [])
        ]
        return payload.get("defaults", {}), specs

    def load_registry(self) -> RegistryConfig:
        """Return validated external registry configuration."""

        payload = json.loads(self._registry_path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            raise ValueError("Unsupported registry config schema_version")
        registry = payload.get("registry", {})
        release = payload.get("release", {})
        config = RegistryConfig(
            provider=registry.get("provider", ""),
            host=registry.get("host", ""),
            namespace=registry.get("namespace", ""),
            project=registry.get("project", ""),
            tag_templates=tuple(release.get("tag_templates", ["{release}-{arch}"])),
        )
        if not config.host:
            raise ValueError("Registry host is required in registry config")
        if not config.namespace:
            raise ValueError("Registry namespace is required in registry config")
        if not config.project:
            raise ValueError("Registry project is required in registry config")
        return config


def select_images(specs: list[ImageSpec], names: list[str]) -> list[ImageSpec]:
    """Select enabled image specifications by public image name or the ``all`` selector."""

    enabled = [spec for spec in specs if spec.enabled]
    if not names or names == ["all"]:
        return enabled
    if "all" in names:
        raise ValueError("IMAGE=all cannot be combined with individual image names")
    wanted = set(names)
    known = {spec.name for spec in specs}
    unknown = wanted - known
    if unknown:
        raise ValueError(f"Unknown image(s): {', '.join(sorted(unknown))}")
    disabled = [spec.name for spec in specs if spec.name in wanted and not spec.enabled]
    if disabled:
        raise ValueError(
            "Requested image(s) are disabled pending Dockerfile verification: "
            + ", ".join(sorted(disabled))
        )
    return [spec for spec in enabled if spec.name in wanted]


def registry_image_reference(
    registry: str,
    namespace: str,
    project: str,
    image: str,
    tag: str,
) -> str:
    """Build one canonical external registry image reference."""

    prefix = registry.rstrip("/")
    path = "/".join(
        part.strip("/") for part in (namespace, project, image) if part.strip("/")
    )
    return f"{prefix}/{path}:{tag}"


def release_tags(config: RegistryConfig, release: str, arch: str) -> list[str]:
    """Render configured release tags while preserving order and removing duplicates."""

    if not release:
        raise ValueError("Release cannot be empty")
    tags = [
        template.format(release=release, arch=arch)
        for template in config.tag_templates
    ]
    return list(dict.fromkeys(tags))
