"""Regression tests for GHCR runtime image selection and Compose overrides."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from deployment.runtime_images import ComposeImageOverrideService, DeploymentImageResolver
from deployment.targets import DeploymentTarget


class RuntimeImageTests(unittest.TestCase):
    """Verify one image manifest drives GHCR installs on local AMD64 and OCI ARM64 hosts."""

    def _repository(self, root: Path) -> Path:
        """Create a minimal deployment repository configuration for isolated tests."""

        (root / "config").mkdir(parents=True)
        (root / "config" / "images.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "images": [
                        {
                            "name": "core",
                            "repository": "agent-nebula-core",
                            "image": "nebula-core",
                            "dockerfile": "Dockerfile",
                            "enabled": True,
                        },
                        {
                            "name": "console",
                            "repository": "agent-nebula-core",
                            "image": "nebula-console",
                            "dockerfile": "Dockerfile",
                            "enabled": True,
                        },
                        {
                            "name": "explorer",
                            "repository": "agent-nebula-explorer",
                            "image": "nebula-explorer",
                            "dockerfile": "Dockerfile",
                            "enabled": True,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        (root / "config" / "registry.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "registry": {
                        "provider": "ghcr",
                        "host": "ghcr.io",
                        "namespace": "example",
                        "project": "agent-nebula",
                    },
                    "release": {"tag_templates": ["{release}-{arch}"]},
                }
            ),
            encoding="utf-8",
        )
        return root

    def test_local_uses_amd64_registry_image(self) -> None:
        """Local laptop deployment consumes the configured GHCR AMD64 image."""

        with tempfile.TemporaryDirectory() as tmp:
            root = self._repository(Path(tmp))
            references = DeploymentImageResolver(root, DeploymentTarget.LOCAL, "0.5.0").references()
            self.assertEqual(
                references["core"],
                "ghcr.io/example/agent-nebula/nebula-core:0.5.0-amd64",
            )

    def test_oci_uses_arm64_registry_image(self) -> None:
        """OCI deployment consumes pushed ARM64 images from configured GHCR namespace."""

        with tempfile.TemporaryDirectory() as tmp:
            root = self._repository(Path(tmp))
            references = DeploymentImageResolver(root, DeploymentTarget.OCI, "0.5.0").references()
            self.assertEqual(
                references["core"],
                "ghcr.io/example/agent-nebula/nebula-core:0.5.0-arm64",
            )

    def test_nebula_override_uses_same_tag_for_services(self) -> None:
        """Generated Compose overrides change images without changing base service topology."""

        with tempfile.TemporaryDirectory() as tmp:
            root = self._repository(Path(tmp))
            destination = root / "override.yml"
            ComposeImageOverrideService(root, DeploymentTarget.LOCAL, "0.5.0").write(
                product="nebula",
                destination=destination,
            )
            text = destination.read_text(encoding="utf-8")
            self.assertIn("nebula-database:\n    image: postgres:17", text)
            self.assertIn(
                "migrate:\n    image: ghcr.io/example/agent-nebula/nebula-core:0.5.0-amd64",
                text,
            )
            self.assertIn(
                "nebula-console:\n    image: ghcr.io/example/agent-nebula/nebula-console:0.5.0-amd64",
                text,
            )

    def test_default_logical_latest_tag_maps_to_architecture_tag(self) -> None:
        """Installation-facing latest resolves to the architecture-specific GHCR tag."""

        with tempfile.TemporaryDirectory() as tmp:
            root = self._repository(Path(tmp))
            local = DeploymentImageResolver(root, DeploymentTarget.LOCAL, "latest").references()
            oci = DeploymentImageResolver(root, DeploymentTarget.OCI, "latest").references()
            self.assertTrue(local["core"].endswith(":latest-amd64"))
            self.assertTrue(oci["core"].endswith(":latest-arm64"))


if __name__ == "__main__":
    unittest.main()
