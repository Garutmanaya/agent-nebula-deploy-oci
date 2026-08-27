"""Compose profile/product environment files from the canonical Utils vocabulary.

Utils owns every ``ANU_*`` name, default, parser, and primitive resolver. Deploy owns only the
product/profile composition that decides which already-defined values belong in a concrete profile
file. Each profile/product receives an isolated file so local, Cloudflare, and Cloud Run settings do
not leak into one another.
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
    StudioEnvironment,
)


@dataclass(frozen=True, slots=True)
class DeploymentEnvironmentFile:
    """Resolved profile/product environment file and its canonical values."""

    path: Path
    values: dict[str, str]


class DeploymentEnvironmentService:
    """Generate isolated profile/product environment files from Utils-owned definitions."""

    _PRODUCTS = frozenset({"nebula", "oauth", "playground", "policy", "studio"})
    _PROFILES = frozenset({"local", "cloudflare", "cloudrun"})

    def __init__(
        self,
        environment: Mapping[str, str] | None = None,
        *,
        target: DeploymentTarget = DeploymentTarget.LOCAL,
    ) -> None:
        """Resolve shared defaults and capture the host/image deployment target."""

        self._infrastructure = anu_load_settings(environment)
        self._deployment = anu_load_deployment_settings(environment)
        self._target = target
        self._files = EnvironmentFileService()

    def generate(
        self,
        *,
        product: str,
        profile: str,
    ) -> DeploymentEnvironmentFile:
        """Regenerate one canonical environment file for a product/profile pair."""

        self._validate_selection(product=product, profile=profile)
        values = self._common_values(profile)
        values.update(self._profile_values(profile))
        if product == "nebula":
            values.update(self._nebula_values(profile, values))
        elif product == "oauth":
            values.update(self._oauth_values(profile, values))
        elif product == "playground":
            values.update(self._playground_values(profile, values))
        elif product == "policy":
            values.update(self._policy_values(profile, values))
        else:
            values.update(self._studio_values(profile))

        destination = self._path(product=product, profile=profile)
        self._files.write(destination, values)
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
            InfrastructureEnvironment.DEPLOYMENT_PROFILE.name: profile,
            InfrastructureEnvironment.RUNTIME_MODE.name: profile,
            DeploymentEnvironment.CONTAINER_UID.name: str(self._deployment.container_uid),
            DeploymentEnvironment.CONTAINER_GID.name: str(self._deployment.container_gid),
            DeploymentEnvironment.IMAGE_SOURCE.name: self._target.image_source,
            DeploymentEnvironment.CORE_IMAGE.name: self._deployment.core_image,
            DeploymentEnvironment.CONSOLE_IMAGE.name: self._deployment.console_image,
            DeploymentEnvironment.EXPLORER_IMAGE.name: self._deployment.explorer_image,
            DeploymentEnvironment.MIGRATION_IMAGE.name: self._deployment.migration_image,
            DeploymentEnvironment.POSTGRES_IMAGE.name: self._deployment.postgres_image,
            DeploymentEnvironment.OAUTH_IMAGE.name: self._deployment.oauth_image,
            DeploymentEnvironment.POLICY_IMAGE.name: self._deployment.policy_image,
            DeploymentEnvironment.STUDIO_IMAGE.name: self._deployment.studio_image,
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

    def _profile_values(self, profile: str) -> dict[str, str]:
        """Return only variables relevant to the selected deployment profile."""

        if profile == "local":
            return {}
        if profile == "cloudflare":
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
                DeploymentEnvironment.CLOUDFLARE_EXPLORER_ORIGIN_URL.name: (
                    self._deployment.cloudflare_explorer_origin_url
                ),
                DeploymentEnvironment.CLOUDFLARE_ORIGIN_SERVER_NAME.name: (
                    self._deployment.cloudflare_origin_server_name
                ),
            }
        return {
            DeploymentEnvironment.GCP_PROJECT.name: self._deployment.gcp_project,
            DeploymentEnvironment.GCP_REGION.name: self._deployment.gcp_region,
            DeploymentEnvironment.GCP_ENVIRONMENT.name: self._deployment.gcp_environment,
            DeploymentEnvironment.GCP_ARTIFACT_REPOSITORY.name: (
                self._deployment.gcp_artifact_repository
            ),
            DeploymentEnvironment.GCP_CLOUD_SQL_TIER.name: self._deployment.gcp_cloud_sql_tier,
            DeploymentEnvironment.GCP_DATABASE_DELETION_PROTECTION.name: str(
                self._deployment.gcp_database_deletion_protection
            ).lower(),
            DeploymentEnvironment.GCP_CORE_MIN_INSTANCES.name: str(
                self._deployment.gcp_core_min_instances
            ),
            DeploymentEnvironment.GCP_CORE_MAX_INSTANCES.name: str(
                self._deployment.gcp_core_max_instances
            ),
            DeploymentEnvironment.GCP_CONSOLE_MIN_INSTANCES.name: str(
                self._deployment.gcp_console_min_instances
            ),
            DeploymentEnvironment.GCP_CONSOLE_MAX_INSTANCES.name: str(
                self._deployment.gcp_console_max_instances
            ),
            DeploymentEnvironment.CLOUDRUN_CORE_SERVICE.name: (
                self._deployment.cloudrun_core_service
            ),
            DeploymentEnvironment.CLOUDRUN_CONSOLE_SERVICE.name: (
                self._deployment.cloudrun_console_service
            ),
            DeploymentEnvironment.CLOUDRUN_EXPLORER_SERVICE.name: (
                self._deployment.cloudrun_explorer_service
            ),
            DeploymentEnvironment.CLOUDRUN_STUDIO_SERVICE.name: (
                self._deployment.cloudrun_studio_service
            ),
            DeploymentEnvironment.CLOUDRUN_MIGRATION_JOB.name: (
                self._deployment.cloudrun_migration_job
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
        if profile == "cloudflare":
            ui_url = "https://agentnebula.ai"
            api_url = "https://api.agentnebula.ai"
            explorer_url = "https://explorer.agentnebula.ai"
            playground_backend_url = "https://pending-playground-backend.invalid"
            database_host = "localhost"
        elif profile == "cloudrun":
            ui_url = "https://pending-ui.invalid"
            api_url = "https://pending-api.invalid"
            explorer_url = "https://pending-explorer.invalid"
            playground_backend_url = "https://pending-playground-backend.invalid"
            database_host = "cloudsql"
        else:
            ui_url = f"https://{hostname}:{ConsoleEnvironment.PORT.default}"
            api_url = f"https://{hostname}:{CoreEnvironment.PORT.default}"
            explorer_url = f"https://{hostname}:{AgentNebulaPorts.EXPLORER}"
            playground_backend_url = (
                f"http://{hostname}:{PlaygroundEnvironment.BACKEND_PORT.default}"
            )
            database_host = hostname

        # Core health probes use backend-reachable topology rather than browser-facing URLs.
        # Local and Cloudflare profiles share the host network; Cloud Run uses the deployed
        # Explorer URL and leaves Playground unknown until a backend service is configured.
        if profile == "cloudrun":
            explorer_health_url = explorer_url
            playground_health_url = ""
        else:
            explorer_health_url = f"https://{hostname}:{AgentNebulaPorts.EXPLORER}"
            playground_health_url = (
                f"http://{hostname}:{PlaygroundEnvironment.BACKEND_PORT.default}"
            )

        environment = dict(base_values)
        environment.update(
            {
                InfrastructureEnvironment.NEBULA_URL.name: api_url,
                CoreEnvironment.PUBLIC_UI_URL.name: ui_url,
                CoreEnvironment.PUBLIC_API_URL.name: api_url,
                CoreEnvironment.DATABASE_HOST.name: database_host,
                CoreEnvironment.HEALTH_EXPLORER_URL.name: explorer_health_url,
                CoreEnvironment.HEALTH_PLAYGROUND_URL.name: playground_health_url,
                OAuthEnvironment.SERVICE_URL.name: oauth_public_url,
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
            DeploymentEnvironment.PUBLIC_UI_HOST.name: (
                ui_url.split("//", 1)[-1].split(":", 1)[0]
            ),
            DeploymentEnvironment.PUBLIC_API_HOST.name: (
                api_url.split("//", 1)[-1].split(":", 1)[0]
            ),
            DeploymentEnvironment.PUBLIC_EXPLORER_HOST.name: (
                explorer_url.split("//", 1)[-1].split(":", 1)[0]
            ),
        }
        values.update(anu_load_core_settings(environment).environment_values())
        values.update(anu_load_console_settings(environment).environment_values())
        values.update(anu_load_explorer_settings(environment).environment_values())
        return values

    def _oauth_public_url(self, profile: str, hostname: str) -> str:
        """Return the canonical browser/client-facing Authorization Server URL."""

        if profile == "cloudflare":
            return "https://oauth.agentnebula.ai"
        if profile == "cloudrun":
            return "https://pending-oauth.invalid"
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
        if profile == "cloudflare":
            registry_url = "https://api.agentnebula.ai"
        elif profile == "cloudrun":
            registry_url = "https://pending-api.invalid"
        else:
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
                OAuthEnvironment.SERVICE_URL.name: public_url,
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
        if profile == "local":
            overrides.update(
                {
                    PlaygroundEnvironment.PUBLIC_URL.name: (
                        f"https://{hostname}:{PlaygroundEnvironment.INGRESS_PORT.default}"
                    ),
                    PlaygroundEnvironment.NEBULA_URL.name: (
                        f"https://{hostname}:{CoreEnvironment.PORT.default}"
                    ),
                    OAuthEnvironment.PUBLIC_URL.name: (
                        f"https://{hostname}:{OAuthEnvironment.PORT.default}"
                    ),
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

    def _studio_values(self, profile: str) -> dict[str, str]:
        """Compose Studio showcase values without defining their environment vocabulary."""

        hostname = self._effective_hostname(profile)
        if profile == "cloudflare":
            public_url = "https://agents.agentnebula.ai"
            nebula_url = "https://api.agentnebula.ai"
        elif profile == "cloudrun":
            public_url = "https://pending-studio.invalid"
            nebula_url = "https://api.agentnebula.ai"
        else:
            public_url = f"https://{hostname}:{StudioEnvironment.INGRESS_PORT.default}"
            nebula_url = f"https://{hostname}:{CoreEnvironment.PORT.default}"
        return {
            OAuthEnvironment.PUBLIC_URL.name: self._oauth_public_url(profile, hostname),
            StudioEnvironment.SHOWCASE.name: self._infrastructure.studio_showcase,
            StudioEnvironment.PUBLIC_URL.name: public_url,
            StudioEnvironment.INGRESS_PORT.name: str(StudioEnvironment.INGRESS_PORT.default),
            StudioEnvironment.SHOWCASE_SANS.name: hostname,
            StudioEnvironment.NEBULA_URL.name: nebula_url,
            StudioEnvironment.STATE_BACKEND.name: (
                StudioEnvironment.STATE_BACKEND.default if profile != "cloudrun" else "firestore"
            ),
            StudioEnvironment.CREDENTIAL_BACKEND.name: StudioEnvironment.CREDENTIAL_BACKEND.default,
            StudioEnvironment.FIRESTORE_PROJECT.name: self._deployment.gcp_project,
            StudioEnvironment.FIRESTORE_COLLECTION.name: (
                StudioEnvironment.FIRESTORE_COLLECTION.default
            ),
            StudioEnvironment.SECRET_MANAGER_PROJECT.name: self._deployment.gcp_project,
        }

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
