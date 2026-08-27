"""Unit tests for independent Cloudflare Tunnel host integration."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from deployment.cloudflare import CloudflareTunnelService
from deployment.targets import DeploymentTarget


class RecordingRunner:
    """Capture Cloudflare adapter invocations without touching systemd."""

    def __init__(self) -> None:
        """Initialize empty invocation state."""

        self.argv: tuple[str, ...] | None = None
        self.environment: dict[str, str] | None = None

    def run(self, argv: tuple[str, ...], *, environment) -> None:
        """Record one command and environment."""

        self.argv = argv
        self.environment = dict(environment)


class CloudflareTunnelTests(unittest.TestCase):
    """Verify Cloudflare remains independent while using canonical profile settings."""

    def test_init_generates_profile_and_invokes_existing_setup_adapter(self) -> None:
        """Cloudflare init must generate the profile and delegate to setup.sh."""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "cloud" / "cloudflare" / "setup.sh"
            script.parent.mkdir(parents=True)
            script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            runner = RecordingRunner()
            old_home = os.environ.get("ANU_HOME")
            old_runtime = os.environ.get("ANU_RUNTIME_HOME")
            try:
                os.environ["ANU_HOME"] = str(root / "opt")
                os.environ["ANU_RUNTIME_HOME"] = str(root / "run")
                CloudflareTunnelService(root, DeploymentTarget.LOCAL, runner).execute("init")
            finally:
                if old_home is None:
                    os.environ.pop("ANU_HOME", None)
                else:
                    os.environ["ANU_HOME"] = old_home
                if old_runtime is None:
                    os.environ.pop("ANU_RUNTIME_HOME", None)
                else:
                    os.environ["ANU_RUNTIME_HOME"] = old_runtime
            self.assertEqual(runner.argv, (str(script), "init"))
            self.assertEqual(runner.environment["ANU_DEPLOYMENT_PROFILE"], "cloudflare")
            self.assertTrue((root / "opt" / "deploy" / "cloudflare" / "nebula.env").is_file())


if __name__ == "__main__":
    unittest.main()
