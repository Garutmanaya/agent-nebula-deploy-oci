"""Unit tests for the Terraform-facing OCI remote application deployment plan."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from deployment.remote_application import (
    OciRemoteApplicationInstaller,
    RemoteApplicationConfiguration,
)


class RemoteApplicationPlanTests(unittest.TestCase):
    """Verify phase composition without opening SSH connections."""

    def _installer(self, phase: str) -> OciRemoteApplicationInstaller:
        """Create one installer using temporary valid repository/key fixtures."""

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        repository = root / "deploy"
        utils = root / "utils"
        repository.mkdir()
        utils.mkdir()
        (repository / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")
        (repository / "config").mkdir()
        (repository / "config" / "registry.json").write_text(
            json.dumps(
                {
                    "registry": {
                        "host": "ghcr.io",
                        "namespace": "example",
                        "project": "agent-nebula",
                    }
                }
            ),
            encoding="utf-8",
        )
        (utils / "pyproject.toml").write_text("[project]\nname='utils'\n", encoding="utf-8")
        identity = root / "id_ed25519"
        identity.write_text("test", encoding="utf-8")
        return OciRemoteApplicationInstaller(
            RemoteApplicationConfiguration(
                host="203.0.113.10",
                user="ubuntu",
                identity_file=identity,
                repository_root=repository,
                utils_repository=utils,
                release="0.5.0",
                profile="local",
                phase=phase,
                compartment_ocid="ocid1.compartment.test",
                vault_ocid="ocid1.vault.test",
                vault_key_ocid="ocid1.key.test",
            )
        )

    def test_platform_phase_preserves_existing_bootstrap_boundary(self) -> None:
        """Platform phase must stop after the existing interactive platform bootstrap."""

        commands = self._installer("platform")._phase_commands()
        text = "\n".join(command for command, _interactive in commands)
        self.assertIn("PRODUCT=policy", text)
        self.assertIn("PRODUCT=nebula", text)
        self.assertIn("PRODUCT=oauth", text)
        self.assertIn(" bootstrap ", text)
        self.assertNotIn("PRODUCT=playground", text)
        self.assertTrue(commands[-1][1])

    def test_application_phase_deploys_explorer_before_playground(self) -> None:
        """Second phase must honor the existing Explorer/Playground post-key deployment order."""

        commands = self._installer("applications")._phase_commands()
        text = "\n".join(command for command, _interactive in commands)
        self.assertLess(text.index("COMPONENT=explorer"), text.index("PRODUCT=playground"))
        self.assertNotIn("make bootstrap", text)


if __name__ == "__main__":
    unittest.main()
