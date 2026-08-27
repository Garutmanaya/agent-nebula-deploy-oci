#!/usr/bin/env python3
"""Product-specific lifecycle adapter behind the generic ``anu`` CLI.

Utils dispatches generic commands. This module owns local/OCI host topology, Compose service names,
application prerequisites, destructive cleanup scope, and application-specific health semantics.
"""

from __future__ import annotations

import argparse
import os
import shutil
import ssl
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from deployment.runtime_images import ComposeImageOverrideService
from deployment.targets import DeploymentTarget

from agent_nebula_utils import (
    HEALTH_ENDPOINTS,
    InitializationForceScope,
    anu_load_core_settings,
    anu_load_explorer_settings,
    anu_load_oauth_settings,
    anu_load_playground_settings,
    anu_load_policy_settings,
    anu_load_settings,
)
from agent_nebula_utils.environment import AgentNebulaSettings
from agent_nebula_utils.environment.definitions import CoreEnvironment

from .environment import DeploymentEnvironmentFile, DeploymentEnvironmentService
from .support.bootstrap import (
    NebulaBootstrapService,
    OAuthBootstrapService,
    PlaygroundBootstrapService,
    PolicyBootstrapService,
)


@dataclass(frozen=True, slots=True)
class ComposeProduct:
    """Product-specific Compose metadata owned by Deploy."""

    file: Path
    services: tuple[str, ...]


class HostDeploymentService:
    """Execute the proven local/Cloudflare Compose lifecycle using canonical Utils settings."""

    def __init__(
        self,
        repository_root: Path,
        *,
        target: DeploymentTarget,
        release: str,
    ) -> None:
        """Capture host target, release, repository paths, and lifecycle collaborators."""

        self._root = repository_root
        self._target = target
        self._release = release
        self._environments = DeploymentEnvironmentService(target=target)
        self._image_overrides = ComposeImageOverrideService(repository_root, target, release)
        self._products = {
            "nebula": ComposeProduct(
                file=self._root / "deploy" / "compose" / "compose.yml",
                services=(
                    "nebula-database",
                    "migrate",
                    "nebula-core",
                    "nebula-console",
                    "nebula-explorer",
                ),
            ),
            "oauth": ComposeProduct(
                file=self._root / "deploy" / "oauth" / "compose.yml",
                services=("nebula-oauth",),
            ),
            "playground": ComposeProduct(
                file=self._root / "deploy" / "playground" / "compose.yml",
                services=(
                    "playground-container",
                    "playground-backend",
                    "playground-ui",
                ),
            ),
            "policy": ComposeProduct(
                file=self._root / "deploy" / "policy" / "compose.yml",
                services=("nebula-policy",),
            ),
        }

    def run(
        self,
        *,
        action: str,
        product: str,
        profile: str,
        component: str | None,
        force_scope: InitializationForceScope | None,
    ) -> bool:
        """Execute one host lifecycle operation and report whether the scope applies."""

        if profile not in {"local", "cloudflare"}:
            raise ValueError(f"Host Compose adapter cannot execute profile {profile!r}")
        if action == "init":
            return self._initialize(
                product=product,
                profile=profile,
                component=component,
                force_scope=force_scope,
            )

        environment = self._environments.load(product=product, profile=profile)
        if action == "deploy":
            if product == "nebula" and component is None:
                self._deploy_nebula_stack(profile, environment, recreate=False)
            else:
                self._deploy(product, environment, component=component, recreate=False)
        elif action == "redeploy":
            if product == "nebula" and component is None:
                self._deploy_nebula_stack(profile, environment, recreate=True)
            else:
                self._deploy(product, environment, component=component, recreate=True)
        elif action == "stop":
            if product == "nebula" and component is None:
                self._stop_nebula_stack(profile, environment)
            else:
                self._compose(product, environment, "stop", *self._service_args(product, component))
        elif action == "health":
            self._health(product, environment, component=component)
        elif action == "logs":
            self._compose(
                product,
                environment,
                "logs",
                "--tail=150",
                *self._service_args(product, component),
            )
        elif action == "destroy":
            self._destroy(product, profile, environment, component=component)
        else:
            return False
        return True

    def _initialize(
        self,
        *,
        product: str,
        profile: str,
        component: str | None,
        force_scope: InitializationForceScope | None,
    ) -> bool:
        """Refresh config and initialize the selected durable resource scope safely."""

        generated = self._environments.generate(product=product, profile=profile)
        if product == "nebula":
            applicable = NebulaBootstrapService(generated.values).initialize(
                force_scope=force_scope,
                component=component,
            )
        elif product == "oauth":
            applicable = OAuthBootstrapService(generated.values).initialize(
                force_scope=force_scope,
                component=component,
            )
        elif product == "playground":
            applicable = PlaygroundBootstrapService(generated.values).initialize(
                force_scope=force_scope,
                component=component,
            )
        elif product == "policy":
            applicable = PolicyBootstrapService(generated.values).initialize(
                force_scope=force_scope,
                component=component,
            )
        else:
            return False
        if applicable:
            force_label = force_scope.value if force_scope else "config"
            print(
                f"Initialized product={product} profile={profile} "
                f"component={component or 'all'} force={force_label} "
                f"environment={generated.path}"
            )
        return applicable

    def _deploy_nebula_stack(
        self,
        profile: str,
        environment: DeploymentEnvironmentFile,
        *,
        recreate: bool,
    ) -> None:
        """Start the local Nebula stack in dependency order across Compose products."""

        policy_environment = self._environments.load(product="policy", profile=profile)
        oauth_environment = self._environments.load(product="oauth", profile=profile)

        # Policy must be available before Registry/Core composes its external policy client.
        self._deploy("policy", policy_environment, component=None, recreate=recreate)
        self._health("policy", policy_environment, component=None)

        # Starting Core brings up PostgreSQL and migrations through Compose dependencies.
        self._deploy("nebula", environment, component="core", recreate=recreate)
        self._health("nebula", environment, component="core")

        # OAuth depends on both Registry resource metadata and external Policy authorization.
        self._deploy("oauth", oauth_environment, component=None, recreate=recreate)
        self._health("oauth", oauth_environment, component=None)

        # User-facing dependents start only after their backing services are ready.
        self._deploy("nebula", environment, component="console", recreate=recreate)
        if self._nonempty(self._explorer_onboarding_key(environment)):
            self._deploy("nebula", environment, component="explorer", recreate=recreate)

    def _stop_nebula_stack(
        self,
        profile: str,
        environment: DeploymentEnvironmentFile,
    ) -> None:
        """Stop the local Nebula stack in reverse dependency order."""

        oauth_environment = self._environments.load(product="oauth", profile=profile)
        policy_environment = self._environments.load(product="policy", profile=profile)

        if self._nonempty(self._explorer_onboarding_key(environment)):
            self._compose(
                "nebula",
                environment,
                "--profile",
                "explorer",
                "stop",
                "nebula-explorer",
            )
        self._compose("nebula", environment, "stop", "nebula-console")
        self._compose("oauth", oauth_environment, "stop", "nebula-oauth")
        self._compose("nebula", environment, "stop", "nebula-core", "nebula-database")
        self._compose("policy", policy_environment, "stop", "nebula-policy")

    def _deploy(
        self,
        product: str,
        environment: DeploymentEnvironmentFile,
        *,
        component: str | None,
        recreate: bool,
    ) -> None:
        """Pull when required, validate prerequisites, and start requested Compose services."""

        if product == "nebula" and component in {None, "core", "migrate", "console", "explorer"}:
            self._require_policy_ready(environment)
        if product == "nebula" and component in {None, "explorer"}:
            if component == "explorer":
                self._require_oauth_ready(environment)
            explorer_key = self._explorer_onboarding_key(environment)
            if component == "explorer" and not self._nonempty(explorer_key):
                raise RuntimeError(
                    "Capability Explorer onboarding API key is missing. Create a Provider API key "
                    "in the Agent Nebula Console and save it to the Explorer secrets directory."
                )
        if product == "oauth":
            self._require_policy_ready(environment)
            self._require_oauth_registry_ready(environment)
        if product == "playground":
            self._require_playground_onboarding_key(environment)

        profiles: tuple[str, ...] = ()
        explorer_enabled = component == "explorer" or self._nonempty(
            self._explorer_onboarding_key(environment)
        )
        if product == "nebula" and explorer_enabled:
            profiles = ("--profile", "explorer")
        services = self._service_args(product, component)
        if self._target is DeploymentTarget.OCI:
            self._compose(product, environment, *profiles, "pull", *services)

        command = [*profiles, "up", "-d"]
        if recreate:
            command.append("--force-recreate")
        command.append("--wait")
        command.extend(services)
        self._compose(product, environment, *command)

    def _destroy(
        self,
        product: str,
        profile: str,
        environment: DeploymentEnvironmentFile,
        *,
        component: str | None,
    ) -> None:
        """Remove services and the durable product/component state owned by this deployment.

        The shared Nebula CA is intentionally retained because it may be consumed by another
        product. Product databases, secrets, certificates, and generated environment files are
        removed when their owning scope is destroyed.
        """

        settings = anu_load_settings(environment.values)
        services = self._service_args(product, component)
        if component is None:
            self._compose(product, environment, "down", "--remove-orphans")
        else:
            self._compose(product, environment, "stop", *services)
            self._compose(product, environment, "rm", "-f", *services)

        for target in self._durable_targets(product, component, environment):
            shutil.rmtree(target, ignore_errors=True)
        if component is None:
            self._environments.remove(product=product, profile=profile)
            self._remove_shared_ca_when_unused(settings, environment)

    def _durable_targets(
        self,
        product: str,
        component: str | None,
        environment: DeploymentEnvironmentFile,
    ) -> tuple[Path, ...]:
        """Return durable roots removed by the selected application lifecycle scope."""

        settings = anu_load_settings(environment.values)
        if product == "oauth":
            return (settings.home / "oauth",) if component in {None, "service"} else ()
        if product == "policy":
            return (settings.home / "policy",) if component in {None, "service"} else ()
        if product == "playground":
            if component is None:
                return (settings.home / "playground",)
            if component not in {"container", "backend", "ui"}:
                return ()
            return (settings.home / "playground" / component,)
        if product != "nebula":
            return ()
        if component is None:
            # Database and Explorer are top-level filesystem owners even though the proven Nebula
            # Compose lifecycle continues to coordinate them as platform components.
            return (
                settings.home / settings.nebula_dir,
                settings.home / "database",
                settings.home / "explorer",
            )
        mapping = {
            "database": settings.home / "database",
            "core": settings.home / settings.nebula_dir / "core",
            "console": settings.home / settings.nebula_dir / "console",
            "explorer": settings.home / "explorer",
        }
        target = mapping.get(component)
        return () if target is None else (target,)

    @staticmethod
    def _remove_shared_ca_when_unused(
        settings: AgentNebulaSettings,
        environment: DeploymentEnvironmentFile,
    ) -> None:
        """Remove the shared CA only after every supported durable product root is absent."""

        roots = (
            settings.home / settings.nebula_dir,
            settings.home / "database",
            settings.home / "explorer",
            settings.home / "playground",
            settings.home / "oauth",
            settings.home / "policy",
        )
        if any(root.exists() for root in roots):
            return
        shutil.rmtree(settings.home / settings.nebula_ca_dir, ignore_errors=True)

    def _health(
        self,
        product: str,
        environment: DeploymentEnvironmentFile,
        *,
        component: str | None,
    ) -> None:
        """Apply application-owned health semantics using canonical endpoint vocabulary."""

        infrastructure = anu_load_settings(environment.values)
        ca_file = (
            infrastructure.home
            / infrastructure.nebula_ca_dir
            / infrastructure.certs_dir
            / infrastructure.root_ca_filename
        )
        if product == "oauth":
            oauth = anu_load_oauth_settings(environment.values)
            context = ssl.create_default_context(cafile=str(ca_file))
            self._probe(f"{oauth.service_url}{HEALTH_ENDPOINTS.ready}", context)
            print("Agent Nebula OAuth health check passed.")
            return
        if product == "policy":
            policy = anu_load_policy_settings(environment.values)
            context = ssl.create_default_context(cafile=str(ca_file))
            self._probe(f"{policy.service_url}{HEALTH_ENDPOINTS.ready}", context)
            print("Agent Nebula Policy health check passed.")
            return

        if infrastructure.deployment_profile == "cloudflare":
            context = ssl.create_default_context()
        else:
            context = ssl.create_default_context(cafile=str(ca_file))
        if product == "playground":
            playground = anu_load_playground_settings(environment.values)
            targets = {
                "container": f"{playground.public_url}{HEALTH_ENDPOINTS.live}",
                "backend": f"{playground.backend_public_url}{HEALTH_ENDPOINTS.live}",
                "ui": f"{playground.ui_public_url}{HEALTH_ENDPOINTS.live}",
            }
            if component is not None:
                target = targets.get(component)
                if target is None:
                    raise ValueError(f"Health is not defined for component {component!r}")
                self._probe(target, context)
            else:
                for target in targets.values():
                    self._probe(target, context)
            print("Agent Nebula Playground health checks passed.")
            return

        core = anu_load_core_settings(environment.values)
        explorer = anu_load_explorer_settings(environment.values)
        core_url = environment.values[CoreEnvironment.PUBLIC_API_URL.name].rstrip("/")
        targets = {
            "core": f"{core_url}{HEALTH_ENDPOINTS.ready}",
            "console": f"{core.public_ui_url}{HEALTH_ENDPOINTS.live}",
            "explorer": f"{explorer.public_url}{HEALTH_ENDPOINTS.live}",
        }
        if component is not None:
            target = targets.get(component)
            if target is None:
                raise ValueError(f"Health is not defined for component {component!r}")
            self._probe(target, context)
        else:
            self._probe(targets["core"], context)
            self._probe(targets["console"], context)
            if self._nonempty(self._explorer_onboarding_key(environment)):
                self._probe(targets["explorer"], context)
        print("Agent Nebula health checks passed.")

    def _compose(
        self,
        product: str,
        environment: DeploymentEnvironmentFile,
        *arguments: str,
    ) -> None:
        """Execute Docker Compose with only the selected profile/product environment file."""

        product_definition = self._products[product]
        process_environment = os.environ.copy()
        process_environment.update(environment.values)
        image_override = self._image_overrides.write(
            product=product,
            destination=(
                environment.path.parent
                / f"{product}.{self._target.value}.{self._release}.images.yml"
            ),
        )
        subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                str(environment.path),
                "-f",
                str(product_definition.file),
                "-f",
                str(image_override),
                *arguments,
            ],
            cwd=self._root,
            env=process_environment,
            check=True,
        )

    def _service_args(self, product: str, component: str | None) -> tuple[str, ...]:
        """Map public component identifiers to current Compose service names."""

        if component is None:
            return ()
        mappings = {
            "nebula": {
                "database": "nebula-database",
                "migrate": "migrate",
                "core": "nebula-core",
                "console": "nebula-console",
                "explorer": "nebula-explorer",
            },
            "playground": {
                "container": "playground-container",
                "backend": "playground-backend",
                "ui": "playground-ui",
            },
            "oauth": {"service": "nebula-oauth"},
            "policy": {"service": "nebula-policy"},
        }
        try:
            return (mappings[product][component],)
        except KeyError as exc:
            raise ValueError(f"Unknown component {component!r} for product {product!r}") from exc

    @staticmethod
    def _probe(url: str, context: ssl.SSLContext) -> None:
        """Execute one health probe and apply the supplied trust context only to HTTPS URLs."""

        if url.lower().startswith("https://"):
            response_context = urllib.request.urlopen(url, context=context, timeout=5)
        else:
            response_context = urllib.request.urlopen(url, timeout=5)
        with response_context as response:
            if response.status >= 400:
                raise RuntimeError(f"Health probe failed: {url}: HTTP {response.status}")

    def _require_policy_ready(self, environment: DeploymentEnvironmentFile) -> None:
        """Require the independently deployed Policy service before starting Registry services."""

        policy = anu_load_policy_settings(environment.values)
        infrastructure = anu_load_settings(environment.values)
        ca_file = (
            infrastructure.home
            / infrastructure.nebula_ca_dir
            / infrastructure.certs_dir
            / infrastructure.root_ca_filename
        )
        context = ssl.create_default_context(cafile=str(ca_file))
        try:
            self._probe(f"{policy.service_url}{HEALTH_ENDPOINTS.ready}", context)
        except Exception as exc:
            raise RuntimeError(
                "Agent Nebula Policy is not ready. Deploy it first with "
                "'make deploy PROFILE=<profile> PRODUCT=policy'."
            ) from exc

    def _require_oauth_registry_ready(self, environment: DeploymentEnvironmentFile) -> None:
        """Require Registry readiness before starting the standalone OAuth service."""

        self._require_registry_ready(environment)

    def _require_registry_ready(self, environment: DeploymentEnvironmentFile) -> None:
        """Require Registry readiness before starting a dependent platform service."""

        infrastructure = anu_load_settings(environment.values)
        core = anu_load_core_settings(environment.values)
        ca_file = (
            infrastructure.home
            / infrastructure.nebula_ca_dir
            / infrastructure.certs_dir
            / infrastructure.root_ca_filename
        )
        context = ssl.create_default_context(cafile=str(ca_file))
        try:
            self._probe(f"{core.public_api_url}{HEALTH_ENDPOINTS.ready}", context)
        except Exception as exc:
            raise RuntimeError(
                "Agent Nebula Registry is not ready. Deploy Nebula Core before this service."
            ) from exc

    def _require_oauth_ready(self, environment: DeploymentEnvironmentFile) -> None:
        """Require standalone OAuth readiness before starting OAuth-dependent services."""

        infrastructure = anu_load_settings(environment.values)
        oauth = anu_load_oauth_settings(environment.values)
        ca_file = (
            infrastructure.home
            / infrastructure.nebula_ca_dir
            / infrastructure.certs_dir
            / infrastructure.root_ca_filename
        )
        context = ssl.create_default_context(cafile=str(ca_file))
        try:
            self._probe(f"{oauth.service_url}{HEALTH_ENDPOINTS.ready}", context)
        except Exception as exc:
            raise RuntimeError(
                "Agent Nebula OAuth is not ready. Deploy OAuth before this service."
            ) from exc

    def _explorer_onboarding_key(self, environment: DeploymentEnvironmentFile) -> Path:
        """Return the canonical Explorer onboarding API-key path from Utils settings."""

        settings = anu_load_settings(environment.values)
        return (
            settings.home
            / "explorer"
            / settings.secrets_dir
            / settings.onboarding_api_key_filename
        )

    def _require_playground_onboarding_key(
        self,
        environment: DeploymentEnvironmentFile,
    ) -> None:
        """Require the operator-created Playground Provider API key before startup."""

        settings = anu_load_settings(environment.values)
        key = (
            settings.home
            / "playground"
            / "container"
            / settings.secrets_dir
            / settings.onboarding_api_key_filename
        )
        if not self._nonempty(key):
            raise RuntimeError(f"Playground onboarding API key is missing or empty: {key}")

    @staticmethod
    def _nonempty(path: Path) -> bool:
        """Return whether a required material file exists and is non-empty."""

        return path.is_file() and path.stat().st_size > 0


def _parse_args() -> argparse.Namespace:
    """Parse manifest-dispatched product lifecycle arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action")
    parser.add_argument("product", choices=("nebula", "oauth", "playground", "policy"))
    parser.add_argument("profile")
    parser.add_argument("--component")
    parser.add_argument(
        "--force",
        choices=tuple(scope.value for scope in InitializationForceScope),
    )
    parser.add_argument(
        "--target",
        choices=tuple(target.value for target in DeploymentTarget),
        default=DeploymentTarget.LOCAL.value,
    )
    parser.add_argument("--release", default="dev")
    return parser.parse_args()


def main() -> int:
    """Run one product lifecycle operation."""

    args = _parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    applicable = HostDeploymentService(
        repository_root,
        target=DeploymentTarget(args.target),
        release=args.release,
    ).run(
        action=args.action,
        product=args.product,
        profile=args.profile,
        component=args.component,
        force_scope=InitializationForceScope(args.force) if args.force else None,
    )
    if not applicable:
        print("Not Applicable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
