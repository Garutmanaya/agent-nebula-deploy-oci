"""Tests for shared image configuration and Buildx command generation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from deployment.images import (
    ImageConfigurationRepository,
    ImageSpec,
    RegistryConfig,
    registry_image_reference,
    release_tags,
    select_images,
)
from scripts.image_pipeline import build_command


class ImagePipelineTests(unittest.TestCase):
    """Verify build and registry behavior remains configuration driven."""

    def test_image_ref(self) -> None:
        """Build GHCR paths using the configured Agent Nebula project prefix."""

        self.assertEqual(
            registry_image_reference(
                "ghcr.io", "example", "agent-nebula", "nebula-policy", "v1-arm64"
            ),
            "ghcr.io/example/agent-nebula/nebula-policy:v1-arm64",
        )

    def test_policy_manifest_is_enabled(self) -> None:
        """Keep Policy enabled with its required named build contexts."""

        root = Path(__file__).parents[1]
        repository = ImageConfigurationRepository(
            root / "config" / "images.json",
            root / "config" / "registry.json",
        )
        defaults, specs = repository.load_manifest()
        policy = next(item for item in specs if item.name == "policy")
        self.assertTrue(policy.enabled)
        self.assertEqual(defaults["platforms"], ["linux/arm64"])
        self.assertIn("agent_nebula_policy_sdk", policy.build_contexts)

    def test_all_selects_all_enabled_images(self) -> None:
        """The all selector must exclude explicitly disabled images."""

        specs = [
            ImageSpec("a", "a", "a", "Dockerfile", enabled=True),
            ImageSpec("b", "b", "b", "Dockerfile", enabled=False),
            ImageSpec("c", "c", "c", "Dockerfile", enabled=True),
        ]
        self.assertEqual([item.name for item in select_images(specs, ["all"])], ["a", "c"])

    def test_all_cannot_be_combined_with_names(self) -> None:
        """Reject ambiguous all-plus-name image selectors."""

        specs = [ImageSpec("a", "a", "a", "Dockerfile")]
        with self.assertRaises(ValueError):
            select_images(specs, ["all", "a"])

    def test_release_tags(self) -> None:
        """Render architecture-specific immutable and latest tags."""

        config = RegistryConfig(
            provider="ghcr",
            host="ghcr.io",
            namespace="example",
            project="agent-nebula",
            tag_templates=("{release}-{arch}", "latest-{arch}"),
        )
        self.assertEqual(release_tags(config, "0.5.0", "arm64"), ["0.5.0-arm64", "latest-arm64"])
        self.assertEqual(release_tags(config, "0.5.0", "amd64"), ["0.5.0-amd64", "latest-amd64"])

    def test_registry_config(self) -> None:
        """Load external registry settings from the shared repository abstraction."""

        payload = {
            "schema_version": 1,
            "registry": {
                "provider": "ghcr",
                "host": "ghcr.io",
                "namespace": "example",
                "project": "agent-nebula",
            },
            "release": {"tag_templates": ["{release}-{arch}"]},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "images.json"
            registry = root / "registry.json"
            manifest.write_text('{"schema_version": 1, "images": []}', encoding="utf-8")
            registry.write_text(json.dumps(payload), encoding="utf-8")
            config = ImageConfigurationRepository(manifest, registry).load_registry()
        self.assertEqual(config.host, "ghcr.io")
        self.assertEqual(config.namespace, "example")
        self.assertEqual(config.project, "agent-nebula")

    def test_multi_platform_load_is_rejected(self) -> None:
        """Docker local load remains single-platform in this workflow."""

        spec = ImageSpec(name="x", repository="x", image="x", dockerfile="Dockerfile")
        with self.assertRaises(ValueError):
            build_command(
                spec=spec,
                repo=Path("/tmp/x"),
                images=["x:dev-arm64"],
                platforms=["linux/amd64", "linux/arm64"],
                push=False,
                load=True,
            )


if __name__ == "__main__":
    unittest.main()
