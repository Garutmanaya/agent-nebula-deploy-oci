"""Regression tests for the corrected local/OCI filesystem ownership model."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[1]
WORKSPACE_ROOT = REPOSITORY_ROOT.parent
UTILS_SOURCE = WORKSPACE_ROOT / "agent-nebula-utils" / "src"
if str(UTILS_SOURCE) not in sys.path:
    sys.path.insert(0, str(UTILS_SOURCE))
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from deployment import AgentNebulaDeploymentTopology, DeploymentFilesystemInitializer


class DeploymentTopologyTests(unittest.TestCase):
    """Verify standalone components no longer inherit the Nebula Core product root."""

    def _topology(self, root: Path) -> AgentNebulaDeploymentTopology:
        """Create one isolated topology rooted under a temporary test directory."""

        return AgentNebulaDeploymentTopology.from_environment(
            {
                "ANU_HOME": str(root / "opt" / "agent-nebula"),
                "ANU_RUNTIME_HOME": str(root / "run" / "agent-nebula"),
            }
        )

    def test_component_roots_follow_corrected_ownership(self) -> None:
        """Core/Console stay grouped while Database and Explorer become standalone products."""

        with tempfile.TemporaryDirectory() as tmp:
            topology = self._topology(Path(tmp))
            home = Path(tmp) / "opt" / "agent-nebula"
            runtime = Path(tmp) / "run" / "agent-nebula"

            self.assertEqual(topology.core.product_root, home / "nebula" / "core")
            self.assertEqual(topology.console.product_root, home / "nebula" / "console")
            self.assertEqual(topology.database.product_root, home / "database")
            self.assertEqual(topology.explorer.product_root, home / "explorer")
            self.assertEqual(topology.oauth.product_root, home / "oauth")
            self.assertEqual(topology.policy.product_root, home / "policy")
            self.assertEqual(topology.database.runtime_root, runtime / "database")
            self.assertEqual(topology.explorer.runtime_root, runtime / "explorer")

    def test_database_credentials_are_owned_by_each_consumer(self) -> None:
        """OAuth and Core must not reference credentials beneath another component root."""

        with tempfile.TemporaryDirectory() as tmp:
            topology = self._topology(Path(tmp))
            credentials = topology.database_credentials

            self.assertEqual(credentials.source, topology.database.secrets / "service-password")
            self.assertEqual(
                credentials.core_destination,
                topology.core.secrets / "database" / "service-password",
            )
            self.assertEqual(
                credentials.oauth_destination,
                topology.oauth.secrets / "database" / "service-password",
            )

    def test_initializer_creates_only_durable_roots(self) -> None:
        """Host initialization must not create container-owned runtime trees."""

        with tempfile.TemporaryDirectory() as tmp:
            topology = self._topology(Path(tmp))
            DeploymentFilesystemInitializer(topology).initialize()

            self.assertTrue(topology.core.data.is_dir())
            self.assertTrue(topology.database.data.is_dir())
            self.assertTrue(topology.explorer.data.is_dir())
            self.assertTrue(topology.oauth.secrets.is_dir())
            self.assertTrue(topology.database_credentials.core_destination.parent.is_dir())
            self.assertTrue(topology.database_credentials.oauth_destination.parent.is_dir())
            self.assertFalse(topology.core.runtime_root.exists())
            self.assertFalse(topology.explorer.runtime_root.exists())

    def test_playground_component_names_are_validated(self) -> None:
        """Reject path-like component names before they can escape the Playground root."""

        with tempfile.TemporaryDirectory() as tmp:
            topology = self._topology(Path(tmp))
            with self.assertRaises(ValueError):
                topology.playground_component("../oauth")


if __name__ == "__main__":
    unittest.main()
