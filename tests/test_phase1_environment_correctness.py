"""Phase 1 regression tests for environment ownership and public/internal endpoints."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from deploy.environment import DeploymentEnvironmentService
from deployment.targets import DeploymentTarget


class Phase1EnvironmentCorrectnessTests(unittest.TestCase):
    """Protect the environment-file ownership and Cloudflare endpoint contracts."""

    def _service(self, root: Path) -> DeploymentEnvironmentService:
        """Create one isolated deployment environment service rooted under ``root``."""

        return DeploymentEnvironmentService(
            {
                "ANU_HOME": str(root / "opt" / "agent-nebula"),
                "ANU_RUNTIME_HOME": str(root / "run" / "agent-nebula"),
                "ANU_DEPLOY_LOCAL_HOSTNAME": "agentnebula-vnic",
            },
            target=DeploymentTarget.OCI,
        )

    def test_component_init_preserves_existing_product_environment(self) -> None:
        """Component-scoped init must not rewrite existing operator-managed product values."""

        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(Path(tmp))
            generated = service.generate(product="nebula", profile="local")
            content = generated.path.read_text()
            content = content.replace(
                "ANU_CONSOLE_API_URL=https://agentnebula-vnic:8000",
                "ANU_CONSOLE_API_URL=https://registry.agentnebula.ai",
            )
            generated.path.write_text(content)

            preserved = service.generate(
                product="nebula",
                profile="local",
                preserve_existing=True,
            )

        self.assertEqual(
            preserved.values["ANU_CONSOLE_API_URL"],
            "https://registry.agentnebula.ai",
        )

    def test_cloudflare_nebula_uses_public_browser_urls_and_internal_service_urls(self) -> None:
        """Cloudflare changes public identity without changing service-to-service topology."""

        with tempfile.TemporaryDirectory() as tmp:
            values = self._service(Path(tmp)).generate(
                product="nebula",
                profile="cloudflare",
            ).values

        self.assertEqual(values["ANU_CORE_PUBLIC_UI_URL"], "https://agentnebula.ai")
        self.assertEqual(
            values["ANU_CORE_PUBLIC_API_URL"],
            "https://registry.agentnebula.ai",
        )
        self.assertEqual(
            values["ANU_CONSOLE_API_URL"],
            "https://registry.agentnebula.ai",
        )
        self.assertEqual(
            values["ANU_NEBULA_URL"],
            "https://agentnebula-vnic:8000",
        )
        self.assertEqual(
            values["ANU_OAUTH_SERVICE_URL"],
            "https://agentnebula-vnic:8092",
        )
        self.assertEqual(
            values["ANU_OAUTH_PUBLIC_URL"],
            "https://oauth.agentnebula.ai",
        )
        self.assertEqual(
            values["ANU_EXPLORER_PUBLIC_URL"],
            "https://agentnebula-vnic:8001",
        )

    def test_cloudflare_oauth_keeps_internal_registry_and_service_urls(self) -> None:
        """OAuth issuer is public while its Registry and service topology remains internal."""

        with tempfile.TemporaryDirectory() as tmp:
            values = self._service(Path(tmp)).generate(
                product="oauth",
                profile="cloudflare",
            ).values

        self.assertEqual(values["ANU_OAUTH_PUBLIC_URL"], "https://oauth.agentnebula.ai")
        self.assertEqual(values["ANU_OAUTH_ISSUER"], "https://oauth.agentnebula.ai")
        self.assertEqual(
            values["ANU_OAUTH_SERVICE_URL"],
            "https://agentnebula-vnic:8092",
        )
        self.assertEqual(
            values["ANU_NEBULA_URL"],
            "https://agentnebula-vnic:8000",
        )


if __name__ == "__main__":
    unittest.main()
