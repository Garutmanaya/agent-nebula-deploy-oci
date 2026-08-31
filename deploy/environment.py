"""Compose profile/product environment files from the canonical Utils vocabulary.

Utils owns every ``ANU_*`` name, default, parser, and primitive resolver. Deploy owns only the
product/profile composition that decides which already-defined values belong in a concrete profile
file. Each profile/product receives an isolated file so private-host and optional Cloudflare public-interface settings do not leak into one another.
"""

from __future__ import annotations

import socket
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_nebula_utils import (
    AgentNebulaPorts,
    anu_load_console_settings,
    anu_load_core_settings,
    anu_load_deployment_settings,
    anu_load_explorer_settings,
    anu_load_oauth_settings,
    anu_load_playground_settings,
    anu_load_policy_settings,
    anu_load_settings,
)
from agent_nebula_utils.environment import EnvironmentFileService
from deployment.runtime_images import DeploymentImageResolver
from deployment.targets import DeploymentTarget

from agent_nebula_utils.environment.definitions import (
    ConsoleEnvironment,
    CoreEnvironment,
    DeploymentEnvironment,
    ExplorerEnvironment,
    FilesystemEnvironment,
    InfrastructureEnvironment,
    OAuthEnvironment,
    PlaygroundEnvironment,
    PolicyEnvironment,
)


@dataclass(frozen=True, slots=True)
class DeploymentEnvironmentFile:
    """Resolved profile/product environment file and its canonical values."""

    path: Path
    values: dict[str, str]


class DeploymentEnvironmentService:
    """Generate isolated profile/product environment files from Utils-owned definitions."""

    _PRODUCTS = frozenset({"nebula", "oauth", "playground", "policy"})
    _PROFILES = frozenset({"local", "cloudflare"})

    def __init__(
        self,
        environment: Mapping[str, str] | None = None,
        *,
        target: DeploymentTarget = DeploymentTarget.LOCAL,
        repository_root: Path | None = None,
        image_tag: str = "latest",
    ) -> None:
        """Resolve shared defaults and capture the host/image deployment target."""

        self._infrastructure = anu_load_settings(environment)
        self._deployment = anu_load_deployment_settings(environment)
        self._target = target
        self._repository_root = repository_root
        self._image_tag = image_tag
        self._files = EnvironmentFileService()

    def generate(
        self,
        *,
        product: str,
        profile: str,
        preserve_existing: bool = False,
    ) -> DeploymentEnvironmentFile:
        """Generate one canonical environment file for a product/profile pair.

        Component-scoped initialization may set ``preserve_existing`` so it consumes the
        established product contract instead of rewriting operator-managed values.
        """

        self._validate_selection(product=product, profile=profile)
        destination = self._path(product=product, profile=profile)
        if preserve_existing and destination.is_file():
            return DeploymentEnvironmentFile(
                path=destination,
                values=self._files.load(destination),
            )
        values = self._common_values(profile)
        values.update(self._image_values(product))
        if product == "nebula":
            values.update(self._profile_values(profile))
            values.update(self._nebula_values(profile, values))
        elif product == "oauth":
            values.update(self._oauth_values(profile, values))
        elif product == "playground":
            values.update(self._playground_values(profile, values))
        elif product == "policy":
            values.update(self._policy_values(profile, values))

        self._files.write_sections(destination, self._categorized_sections(values))
        return DeploymentEnvironmentFile(path=destination, values=values)

    def load(self, *, product: str, profile: str) -> DeploymentEnvironmentFile:
        """Load the environment file associated with exactly one profile/product pair."""

        self._validate_selection(product=product, profile=profile)
        path = self._path(product=product, profile=profile)
        if not path.is_file():
            raise FileNotFoundError(
                f"Run 'anu init --profile {profile} --product {product}' first: {path}"
            )
        return DeploymentEnvironmentFile(path=path, values=self._files.load(path))

    def remove(self, *, product: str, profile: str) -> None:
        """Remove one generated environment file and empty profile/deploy directories."""

        path = self._path(product=product, profile=profile)
        path.unlink(missing_ok=True)
        for directory in (path.parent, path.parent.parent):
            try:
                directory.rmdir()
            except OSError:
                break

    def _path(self, *, product: str, profile: str) -> Path:
        """Return the isolated profile/product environment-file location."""

        return self._infrastructure.home / "deploy" / profile / f"{product}.env"

    def _common_values(self, profile: str) -> dict[str, str]:
        """Return values required by every supported profile."""

        hostname = self._effective_hostname(profile)
        return {
            InfrastructureEnvironment.HOME.name: str(self._infrastructure.home),
            InfrastructureEnvironment.RUNTIME_HOME.name: str(self._infrastructure.runtime_home),
            InfrastructureEnvironment.SECURITY_INPUT_ROOT.name: str(
                self._infrastructure.security_input_root
            ),
            "DEPLOY_SECURITY_SOURCE_ROOT": (
                str(self._infrastructure.home)
                if self._target is DeploymentTarget.LOCAL
                else "/run/agent-nebula-security-staging"
            ),
            "DEPLOY_SECURITY_STAGING_ROOT": "/run/agent-nebula-security-staging",
            InfrastructureEnvironment.DEPLOYMENT_PROFILE.name: profile,
            InfrastructureEnvironment.RUNTIME_MODE.name: "local",
            DeploymentEnvironment.CONTAINER_UID.name: str(self._deployment.container_uid),
            DeploymentEnvironment.CONTAINER_GID.name: str(self._deployment.container_gid),
            DeploymentEnvironment.IMAGE_SOURCE.name: self._target.image_source,
            DeploymentEnvironment.LOCAL_HOSTNAME.name: hostname,
            FilesystemEnvironment.CONFIG_DIR.name: self._infrastructure.config_dir,
            FilesystemEnvironment.SECRETS_DIR.name: self._infrastructure.secrets_dir,
            FilesystemEnvironment.CERTS_DIR.name: self._infrastructure.certs_dir,
            FilesystemEnvironment.DATA_DIR.name: self._infrastructure.data_dir,
            FilesystemEnvironment.LOGS_DIR.name: self._infrastructure.logs_dir,
            FilesystemEnvironment.TMP_DIR.name: self._infrastructure.tmp_dir,
            FilesystemEnvironment.PKI_DIR.name: self._infrastructure.pki_dir,
            FilesystemEnvironment.APPLICATION_CONFIG_FILENAME.name: (
                self._infrastructure.application_config_filename
            ),
            FilesystemEnvironment.ONBOARDING_API_KEY_FILENAME.name: (
                self._infrastructure.onboarding_api_key_filename
            ),
            FilesystemEnvironment.OAUTH_AUTH_KEY_FILENAME.name: (
                self._infrastructure.oauth_auth_key_filename
            ),
            FilesystemEnvironment.OAUTH_DPOP_KEY_FILENAME.name: (
                self._infrastructure.oauth_dpop_key_filename
            ),
            FilesystemEnvironment.TLS_CERT_FILENAME.name: (
                self._infrastructure.tls_cert_filename
            ),
            FilesystemEnvironment.TLS_KEY_FILENAME.name: self._infrastructure.tls_key_filename,
            FilesystemEnvironment.ROOT_CA_FILENAME.name: self._infrastructure.root_ca_filename,
            FilesystemEnvironment.TRUST_BUNDLE_FILENAME.name: (
                self._infrastructure.trust_bundle_filename
            ),
        }

    def _image_values(self, product: str) -> dict[str, str]:
        """Return only effective image references used by the selected product."""

        if self._repository_root is None:
            return {}
        references = DeploymentImageResolver(
            self._repository_root,
            self._target,
            self._image_tag,
        ).references()
        if product == "nebula":
            return {
                DeploymentEnvironment.CORE_IMAGE.name: references["core"],
                DeploymentEnvironment.CONSOLE_IMAGE.name: references["console"],
                DeploymentEnvironment.EXPLORER_IMAGE.name: references["explorer"],
                DeploymentEnvironment.MIGRATION_IMAGE.name: references["core"],
                DeploymentEnvironment.POSTGRES_IMAGE.name: "postgres:17",
            }
        if product == "oauth":
            return {DeploymentEnvironment.OAUTH_IMAGE.name: references["oauth"]}
        if product == "policy":
            return {DeploymentEnvironment.POLICY_IMAGE.name: references["policy"]}
        return {}

    @staticmethod
    def _categorized_sections(values: Mapping[str, str]) -> dict[str, dict[str, str]]:
        """Group generated values using canonical Utils ownership rather than raw prefixes."""

        sections: dict[str, dict[str, str]] = {
            "Deployment": {},
            "Images": {},
            "Filesystem & Runtime": {},
            "Database": {},
            "Core": {},
            "Console": {},
            "Explorer": {},
            "OAuth": {},
            "Policy": {},
            "Playground": {},
            "Cloudflare": {},
            "Integration": {},
            "Other": {},
        }
        filesystem_names = {definition.name for definition in FilesystemEnvironment.definitions()} | {
            InfrastructureEnvironment.HOME.name,
            InfrastructureEnvironment.RUNTIME_HOME.name,
            InfrastructureEnvironment.SECURITY_INPUT_ROOT.name,
        }
        deployment_names = {
            InfrastructureEnvironment.DEPLOYMENT_PROFILE.name,
            InfrastructureEnvironment.RUNTIME_MODE.name,
            DeploymentEnvironment.CONTAINER_UID.name,
            DeploymentEnvironment.CONTAINER_GID.name,
            DeploymentEnvironment.IMAGE_SOURCE.name,
            DeploymentEnvironment.LOCAL_HOSTNAME.name,
        }
        image_names = {
            DeploymentEnvironment.CORE_IMAGE.name,
            DeploymentEnvironment.CONSOLE_IMAGE.name,
            DeploymentEnvironment.EXPLORER_IMAGE.name,
            DeploymentEnvironment.MIGRATION_IMAGE.name,
            DeploymentEnvironment.POSTGRES_IMAGE.name,
            DeploymentEnvironment.OAUTH_IMAGE.name,
            DeploymentEnvironment.POLICY_IMAGE.name,
        }
        core_names = {definition.name for definition in CoreEnvironment.definitions()}
        console_names = {definition.name for definition in ConsoleEnvironment.definitions()}
        explorer_names = {definition.name for definition in ExplorerEnvironment.definitions()}
        oauth_names = {definition.name for definition in OAuthEnvironment.definitions()}
        policy_names = {definition.name for definition in PolicyEnvironment.definitions()}
        playground_names = {definition.name for definition in PlaygroundEnvironment.definitions()}
        cloudflare_names = {
            DeploymentEnvironment.CLOUDFLARE_TUNNEL_NAME.name,
            DeploymentEnvironment.CLOUDFLARE_TUNNEL_ID.name,
            DeploymentEnvironment.CLOUDFLARE_CREDENTIALS_SOURCE.name,
            DeploymentEnvironment.CLOUDFLARE_SERVICE_USER.name,
            DeploymentEnvironment.CLOUDFLARE_SERVICE_GROUP.name,
            DeploymentEnvironment.CLOUDFLARE_FRONTEND_ORIGIN_URL.name,
            DeploymentEnvironment.CLOUDFLARE_BACKEND_ORIGIN_URL.name,
            DeploymentEnvironment.CLOUDFLARE_ORIGIN_SERVER_NAME.name,
        }
        for name, value in values.items():
            if name in image_names:
                section = "Images"
            elif name in filesystem_names or name in {
                "DEPLOY_SECURITY_SOURCE_ROOT",
                "DEPLOY_SECURITY_STAGING_ROOT",
            }:
                section = "Filesystem & Runtime"
            elif name in deployment_names:
                section = "Deployment"
            elif name in core_names:
                section = "Database" if "DATABASE" in name else "Core"
            elif name in console_names:
                section = "Console"
            elif name in explorer_names:
                section = "Explorer"
            elif name in oauth_names:
                section = "Database" if "DATABASE" in name else "OAuth"
            elif name in policy_names:
                section = "Policy"
            elif name in playground_names:
                section = "Playground"
            elif name in cloudflare_names:
                section = "Cloudflare"
            elif name == InfrastructureEnvironment.NEBULA_URL.name:
                section = "Integration"
            else:
                section = "Other"
            sections[section][name] = value
        return sections

    def _profile_values(self, profile: str) -> dict[str, str]:
        """Return optional Cloudflare tunnel settings for the public-interface profile."""

        if profile == "local":
            return {}
        return {
            DeploymentEnvironment.CLOUDFLARE_TUNNEL_NAME.name: (
                self._deployment.cloudflare_tunnel_name
            ),
            DeploymentEnvironment.CLOUDFLARE_TUNNEL_ID.name: (
                self._deployment.cloudflare_tunnel_id
            ),
            DeploymentEnvironment.CLOUDFLARE_CREDENTIALS_SOURCE.name: (
                self._deployment.cloudflare_credentials_source
            ),
            DeploymentEnvironment.CLOUDFLARE_SERVICE_USER.name: (
                self._deployment.cloudflare_service_user
            ),
            DeploymentEnvironment.CLOUDFLARE_SERVICE_GROUP.name: (
                self._deployment.cloudflare_service_group
            ),
            DeploymentEnvironment.CLOUDFLARE_FRONTEND_ORIGIN_URL.name: (
                self._deployment.cloudflare_frontend_origin_url
            ),
            DeploymentEnvironment.CLOUDFLARE_BACKEND_ORIGIN_URL.name: (
                self._deployment.cloudflare_backend_origin_url
            ),
            DeploymentEnvironment.CLOUDFLARE_ORIGIN_SERVER_NAME.name: (
                self._deployment.cloudflare_origin_server_name
            ),
        }

    def _nebula_values(
        self,
        profile: str,
        base_values: Mapping[str, str],
    ) -> dict[str, str]:
        """Resolve complete Core/Console/Explorer settings for one Nebula profile.

        Deploy owns endpoint/topology composition, while Utils owns every variable default,
        parser, validation rule, and canonical serialization. This prevents non-Python runtimes
        such as Console from losing defaulted values when a new environment definition is added.
        """

        hostname = self._effective_hostname(profile)
        oauth_public_url = self._oauth_public_url(profile, hostname)
        oauth_service_url = f"https://{hostname}:{AgentNebulaPorts.OAUTH}"
        if profile == "cloudflare":
            ui_url = "https://agentnebula.ai"
            api_url = "https://registry.agentnebula.ai"
            explorer_url = f"https://{hostname}:{AgentNebulaPorts.EXPLORER}"
            playground_backend_url = (
                f"http://{hostname}:{PlaygroundEnvironment.BACKEND_PORT.default}"
            )
            database_host = hostname
        else:
            ui_url = f"https://{hostname}:{ConsoleEnvironment.PORT.default}"
            api_url = f"https://{hostname}:{CoreEnvironment.PORT.default}"
            explorer_url = f"https://{hostname}:{AgentNebulaPorts.EXPLORER}"
            playground_backend_url = (
                f"http://{hostname}:{PlaygroundEnvironment.BACKEND_PORT.default}"
            )
            database_host = hostname

        # Health dependencies always use backend-reachable host topology. Public Cloudflare
        # identities are browser/client-facing only and do not alter service-to-service routing.
        explorer_health_url = f"https://{hostname}:{AgentNebulaPorts.EXPLORER}"
        playground_health_url = (
            f"http://{hostname}:{PlaygroundEnvironment.BACKEND_PORT.default}"
        )

        environment = dict(base_values)
        environment.update(
            {
                InfrastructureEnvironment.NEBULA_URL.name: (
                    f"https://{hostname}:{CoreEnvironment.PORT.default}"
                    if profile == "cloudflare"
                    else api_url
                ),
                CoreEnvironment.PUBLIC_UI_URL.name: ui_url,
                CoreEnvironment.PUBLIC_API_URL.name: api_url,
                CoreEnvironment.DATABASE_HOST.name: database_host,
                CoreEnvironment.HEALTH_EXPLORER_URL.name: explorer_health_url,
                CoreEnvironment.HEALTH_PLAYGROUND_URL.name: playground_health_url,
                OAuthEnvironment.SERVICE_URL.name: oauth_service_url,
                OAuthEnvironment.PUBLIC_URL.name: oauth_public_url,
                PolicyEnvironment.SERVICE_URL.name: (
                    f"https://{hostname}:{PolicyEnvironment.PORT.default}"
                ),
                CoreEnvironment.DATABASE_PASSWORD_FILE.name: str(
                    self._infrastructure.home
                    / self._infrastructure.nebula_dir
                    / "core"
                    / self._infrastructure.secrets_dir
                    / "database"
                    / "service-password"
                ),
                ConsoleEnvironment.API_URL.name: api_url,
                ConsoleEnvironment.EXPLORER_URL.name: explorer_url,
                ConsoleEnvironment.PLAYGROUND_URL.name: playground_backend_url,
                ConsoleEnvironment.EXPLORER_CA_CERTS.name: str(
                    self._infrastructure.home
                    / self._infrastructure.nebula_ca_dir
                    / self._infrastructure.certs_dir
                    / self._infrastructure.root_ca_filename
                ),
                ExplorerEnvironment.MODE.name: "capability-explorer",
                ExplorerEnvironment.PUBLIC_URL.name: explorer_url,
                ExplorerEnvironment.ALLOWED_ORIGINS.name: ui_url,
            }
        )

        values = {
            OAuthEnvironment.SERVICE_URL.name: environment[OAuthEnvironment.SERVICE_URL.name],
            OAuthEnvironment.PUBLIC_URL.name: environment[OAuthEnvironment.PUBLIC_URL.name],
            PolicyEnvironment.SERVICE_URL.name: environment[PolicyEnvironment.SERVICE_URL.name],
        }
        values.update(anu_load_core_settings(environment).environment_values())
        values.update(anu_load_console_settings(environment).environment_values())
        values.update(anu_load_explorer_settings(environment).environment_values())
        return values

    def _oauth_public_url(self, profile: str, hostname: str) -> str:
        """Return the browser/client-facing Authorization Server identity."""

        if profile == "cloudflare":
            return "https://oauth.agentnebula.ai"
        return self._oauth_service_url(hostname)

    @staticmethod
    def _oauth_service_url(hostname: str) -> str:
        """Return the backend-reachable OAuth endpoint used by platform services."""

        return f"https://{hostname}:{AgentNebulaPorts.OAUTH}"

    def _oauth_values(
        self,
        profile: str,
        base_values: Mapping[str, str],
    ) -> dict[str, str]:
        """Compose standalone OAuth topology from canonical Utils definitions."""

        hostname = self._effective_hostname(profile)
        overrides = dict(base_values)
        public_url = self._oauth_public_url(profile, hostname)
        registry_url = f"https://{hostname}:{CoreEnvironment.PORT.default}"

        database_password_file = (
            self._infrastructure.home
            / "oauth"
            / self._infrastructure.secrets_dir
            / "database"
            / "service-password"
        )
        overrides.update(
            {
                InfrastructureEnvironment.NEBULA_URL.name: registry_url,
                OAuthEnvironment.SERVICE_URL.name: (
                    f"https://{hostname}:{AgentNebulaPorts.OAUTH}"
                ),
                OAuthEnvironment.PUBLIC_URL.name: public_url,
                OAuthEnvironment.ISSUER.name: public_url,
                OAuthEnvironment.HOST.name: "0.0.0.0",
                OAuthEnvironment.PORT.name: str(OAuthEnvironment.PORT.default),
                OAuthEnvironment.TLS_ENABLED.name: "true",
                OAuthEnvironment.DATABASE_HOST.name: hostname,
                OAuthEnvironment.DATABASE_PORT.name: str(CoreEnvironment.DATABASE_PORT.default),
                OAuthEnvironment.DATABASE_NAME.name: CoreEnvironment.DATABASE_NAME.default,
                OAuthEnvironment.DATABASE_USER.name: CoreEnvironment.DATABASE_USER.default,
                OAuthEnvironment.DATABASE_PASSWORD_FILE.name: str(database_password_file),
                OAuthEnvironment.DATABASE_SSL_MODE.name: CoreEnvironment.DATABASE_SSL_MODE.default,
                PolicyEnvironment.SERVICE_URL.name: (
                    f"https://{hostname}:{PolicyEnvironment.PORT.default}"
                ),
            }
        )
        return anu_load_oauth_settings(overrides).environment_values() | {
            InfrastructureEnvironment.NEBULA_URL.name: registry_url,
            PolicyEnvironment.SERVICE_URL.name: overrides[PolicyEnvironment.SERVICE_URL.name],
        }

    def _playground_values(
        self,
        profile: str,
        base_values: Mapping[str, str],
    ) -> dict[str, str]:
        """Compose Playground service URLs from the canonical Utils vocabulary."""

        hostname = self._effective_hostname(profile)
        overrides = dict(base_values)
        explorer_environment = dict(base_values)
        explorer_environment.update(
            {
                InfrastructureEnvironment.NEBULA_URL.name: (
                    f"https://{hostname}:{CoreEnvironment.PORT.default}"
                ),
                ExplorerEnvironment.MODE.name: "capability-explorer",
                ExplorerEnvironment.PUBLIC_URL.name: f"https://{hostname}",
            }
        )
        explorer = anu_load_explorer_settings(explorer_environment)
        if profile in {"local", "cloudflare"}:
            overrides.update(
                {
                    PlaygroundEnvironment.PUBLIC_URL.name: (
                        f"https://{hostname}:{PlaygroundEnvironment.INGRESS_PORT.default}"
                    ),
                    PlaygroundEnvironment.NEBULA_URL.name: (
                        f"https://{hostname}:{CoreEnvironment.PORT.default}"
                    ),
                    OAuthEnvironment.PUBLIC_URL.name: self._oauth_public_url(profile, hostname),
                    PlaygroundEnvironment.HOST.name: "127.0.0.1",
                    PlaygroundEnvironment.BACKEND_PUBLIC_URL.name: (
                        f"http://{hostname}:{PlaygroundEnvironment.BACKEND_PORT.default}"
                    ),
                    PlaygroundEnvironment.BACKEND_HOST.name: "0.0.0.0",
                    PlaygroundEnvironment.UI_PUBLIC_URL.name: (
                        f"https://{hostname}:{PlaygroundEnvironment.UI_PORT.default}"
                    ),
                    PlaygroundEnvironment.UI_BACKEND_URL.name: (
                        f"http://127.0.0.1:{PlaygroundEnvironment.BACKEND_PORT.default}"
                    ),
                    PlaygroundEnvironment.UI_EXPLORER_URL.name: (
                        f"https://{hostname}:{explorer.port}"
                    ),
                    PlaygroundEnvironment.UI_SSL_ENABLED.name: "true",
                }
            )
        return anu_load_playground_settings(overrides).environment_values() | {
            OAuthEnvironment.PUBLIC_URL.name: overrides[OAuthEnvironment.PUBLIC_URL.name],
        }

    def _policy_values(
        self,
        profile: str,
        base_values: Mapping[str, str],
    ) -> dict[str, str]:
        """Compose standalone Policy endpoint and OPA runtime values from Utils definitions."""

        hostname = self._effective_hostname(profile)
        overrides = dict(base_values)
        overrides.update(
            {
                PolicyEnvironment.SERVICE_URL.name: (
                    f"https://{hostname}:{PolicyEnvironment.PORT.default}"
                ),
                PolicyEnvironment.HOST.name: "0.0.0.0",
                PolicyEnvironment.PORT.name: str(PolicyEnvironment.PORT.default),
                PolicyEnvironment.TLS_ENABLED.name: "true",
                PolicyEnvironment.OPA_MODE.name: "embedded",
                PolicyEnvironment.OPA_BASE_URL.name: PolicyEnvironment.OPA_BASE_URL.default,
            }
        )
        return anu_load_policy_settings(overrides).environment_values()

    def _effective_hostname(self, profile: str) -> str:
        """Return the profile hostname used for local direct-TLS endpoints."""

        hostname = self._deployment.local_hostname
        if profile == "local" and hostname == "localhost":
            return socket.gethostname().split(".", 1)[0] or "localhost"
        return hostname

    def _validate_selection(self, *, product: str, profile: str) -> None:
        """Reject unknown product/profile names before touching the filesystem."""

        if product not in self._PRODUCTS:
            raise ValueError(f"Unsupported deployment product: {product}")
        if profile not in self._PROFILES:
            raise ValueError(f"Unsupported deployment profile: {profile}")
