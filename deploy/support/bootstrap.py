"""Agent Nebula deployment initialization composed from shared Utils primitives.

This module owns only product topology and deployment intent. Generic filesystem,
PKI, environment, and filename mechanics are delegated to ``agent-nebula-utils``.
The generic lifecycle engine and public ``anu`` deployment CLI are intentionally
out of scope for Phase 1 and will be added in Step 8.
"""

from __future__ import annotations

import secrets
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from agent_nebula_utils import (
    CertificateAuthorityPaths,
    CertificateIdentityPaths,
    CertificateRequestOptions,
    CertificateSubject,
    DeploymentDirectory,
    DeploymentSecurityPaths,
    InitializationForceScope,
    OpenSslExecutor,
    anu_ca_paths,
    anu_deployment_directory,
    anu_ensure_local_ca,
    anu_initialize_durable_directory,
    anu_initialize_runtime_directory,
    anu_issue_local_server_certificate,
    anu_load_core_settings,
    anu_load_oauth_settings,
    anu_load_playground_settings,
    anu_load_policy_settings,
    anu_load_settings,
    anu_load_studio_settings,
)
from agent_nebula_utils.environment import AgentNebulaSettings

from deployment.topology import AgentNebulaDeploymentTopology


@dataclass(frozen=True, slots=True)
class NebulaDeploymentTopology:
    """Expose corrected Core/Console/Database/Explorer placement to bootstrap services."""

    settings: AgentNebulaSettings

    @property
    def _deployment(self) -> AgentNebulaDeploymentTopology:
        """Return the canonical deployment topology shared by local and OCI targets."""

        return AgentNebulaDeploymentTopology(self.settings)

    @property
    def core(self) -> DeploymentDirectory:
        """Return the Core deployment directory."""

        return self._deployment.core

    @property
    def console(self) -> DeploymentDirectory:
        """Return the Console deployment directory."""

        return self._deployment.console

    @property
    def explorer(self) -> DeploymentDirectory:
        """Return the standalone Explorer deployment directory."""

        return self._deployment.explorer

    @property
    def database(self) -> DeploymentDirectory:
        """Return the standalone PostgreSQL deployment directory."""

        return self._deployment.database


@dataclass(frozen=True, slots=True)
class PolicyDeploymentTopology:
    """Resolve durable/runtime roots for the standalone Policy product."""

    settings: AgentNebulaSettings
    instance: str

    @property
    def service(self) -> DeploymentDirectory:
        """Return the standalone Policy service directory."""

        return AgentNebulaDeploymentTopology(self.settings).policy


@dataclass(frozen=True, slots=True)
class OAuthDeploymentTopology:
    """Resolve durable/runtime roots for the standalone OAuth product."""

    settings: AgentNebulaSettings
    instance: str

    @property
    def service(self) -> DeploymentDirectory:
        """Return the standalone OAuth Authorization Server directory."""

        return AgentNebulaDeploymentTopology(self.settings).oauth


@dataclass(frozen=True, slots=True)
class StudioDeploymentTopology:
    """Resolve the single Studio showcase instance managed by Deploy."""

    settings: AgentNebulaSettings

    @property
    def showcase(self) -> DeploymentDirectory:
        """Return the Studio showcase instance directory using explicit Utils roots."""

        return anu_deployment_directory(
            product_root=(
                self.settings.home
                / self.settings.studio_dir
                / self.settings.studio_showcase
            ),
            runtime_root=(
                self.settings.runtime_home
                / self.settings.studio_dir
                / self.settings.studio_showcase
            ),
            settings=self.settings,
        )


@dataclass(frozen=True, slots=True)
class PlaygroundDeploymentTopology:
    """Resolve host-owned durable roots for the three Playground services.

    Disposable ``/run/agent-nebula/playground`` state is intentionally represented only as
    topology metadata. Deploy never initializes that runtime tree on the host; each container
    creates its own runtime root through Agent Nebula Utils during startup.
    """

    settings: AgentNebulaSettings

    def component(self, name: str) -> DeploymentDirectory:
        """Return one canonical standalone Playground service directory."""

        return AgentNebulaDeploymentTopology(self.settings).playground_component(name)

    @property
    def container(self) -> DeploymentDirectory:
        """Return the controlled experiment-container service directory."""

        return self.component("container")

    @property
    def backend(self) -> DeploymentDirectory:
        """Return the Playground backend service directory."""

        return self.component("backend")

    @property
    def ui(self) -> DeploymentDirectory:
        """Return the Playground UI service directory."""

        return self.component("ui")


class DeploymentLocalPkiService:
    """Apply Deploy-owned identity intent through generic Utils PKI services."""

    def __init__(self, settings: AgentNebulaSettings) -> None:
        """Create a local PKI adapter for one resolved deployment settings snapshot."""

        self._settings = settings
        ca = anu_ca_paths(settings)
        self._ca_directory = anu_deployment_directory(
            product_root=ca.root,
            runtime_root=settings.runtime_home / settings.nebula_ca_dir,
            settings=settings,
        )
        self._ca = CertificateAuthorityPaths(
            certificate=ca.root_certificate,
            private_key=ca.root / settings.secrets_dir / "root-ca.key",
            serial_file=ca.root_certificate.with_suffix(".srl"),
        )
        self._openssl = OpenSslExecutor()

    def ensure_ca(self, *, force: bool) -> CertificateAuthorityPaths:
        """Create or validate the local deployment CA without product logic in Utils."""

        anu_initialize_durable_directory(self._ca_directory)
        if force:
            self._ca.certificate.unlink(missing_ok=True)
            self._ca.private_key.unlink(missing_ok=True)
            if self._ca.serial_file is not None:
                self._ca.serial_file.unlink(missing_ok=True)

        return anu_ensure_local_ca(
            paths=self._ca,
            subject=CertificateSubject(
                common_name="Agent Nebula Platform Root CA",
                organization="Agent Nebula Platform",
            ),
            options=CertificateRequestOptions(key_bits=4096, validity_days=3650),
        )

    def ensure_server_identity(
        self,
        *,
        directory: DeploymentDirectory,
        common_name: str,
        dns_names: tuple[str, ...],
        force: bool,
    ) -> CertificateIdentityPaths:
        """Issue a server identity only when absent, forced, or missing required SANs."""

        security = DeploymentSecurityPaths(directory)
        identity = CertificateIdentityPaths(
            certificate=security.tls_certificate,
            private_key=security.tls_private_key,
        )
        normalized_names = tuple(dict.fromkeys(name for name in dns_names if name))

        if not force and self._identity_matches(identity, normalized_names):
            return identity

        identity.certificate.unlink(missing_ok=True)
        identity.private_key.unlink(missing_ok=True)
        ca_for_issue = self._ca
        if self._ca.serial_file is not None and not self._ca.serial_file.exists():
            ca_for_issue = CertificateAuthorityPaths(
                certificate=self._ca.certificate,
                private_key=self._ca.private_key,
                serial_file=None,
            )

        issued = anu_issue_local_server_certificate(
            ca=ca_for_issue,
            identity=identity,
            subject=CertificateSubject(
                common_name=common_name,
                organization="Agent Nebula Platform",
            ),
            options=CertificateRequestOptions(
                key_bits=3072,
                validity_days=825,
                san_dns_names=("localhost", *normalized_names),
                san_ip_addresses=("127.0.0.1", "::1"),
            ),
        )
        if issued.csr is not None:
            issued.csr.unlink(missing_ok=True)
        return CertificateIdentityPaths(
            certificate=issued.certificate,
            private_key=issued.private_key,
            csr=None,
        )

    def _identity_matches(
        self,
        identity: CertificateIdentityPaths,
        dns_names: tuple[str, ...],
    ) -> bool:
        """Return whether an existing key/certificate pair covers all requested DNS names."""

        if not identity.certificate.is_file() or not identity.private_key.is_file():
            return False
        try:
            for name in dns_names:
                self._openssl.run(
                    "x509",
                    "-in",
                    str(identity.certificate),
                    "-noout",
                    "-checkhost",
                    name,
                )
        except Exception:
            return False
        return True


class NebulaBootstrapService:
    """Initialize durable local/Cloudflare Nebula deployment material idempotently."""

    def __init__(self, environment: Mapping[str, str]) -> None:
        """Resolve shared settings once and compose product-specific initialization services."""

        self._settings = anu_load_settings(environment)
        self._core_settings = anu_load_core_settings(environment)
        self._topology = NebulaDeploymentTopology(self._settings)
        self._pki = DeploymentLocalPkiService(self._settings)
        self._openssl = OpenSslExecutor()
        self._deployment_assets_destination = Path(environment["ANU_HOME"]) / "deploy" / "assets"

    def initialize(
        self,
        *,
        force_scope: InitializationForceScope | None,
        component: str | None = None,
    ) -> bool:
        """Initialize all or one Nebula component using the existing idempotent behavior.

        Missing resources are always created idempotently. Existing resources are replaced only
        when the explicit force category permits it. ``migrate`` has no durable resources and
        therefore returns ``False`` so the public CLI can report ``Not Applicable``.
        """

        directories = {
            "core": self._topology.core,
            "console": self._topology.console,
            "explorer": self._topology.explorer,
            "database": self._topology.database,
        }
        if component == "migrate":
            return False
        if component is None:
            selected = tuple(directories)
        elif component in directories:
            selected = (component,)
        else:
            return False

        force_pki = force_scope in {InitializationForceScope.PKI, InitializationForceScope.ALL}
        force_database = force_scope in {
            InitializationForceScope.DATABASE,
            InitializationForceScope.ALL,
        }
        force_secrets = force_scope is InitializationForceScope.ALL
        # Validate disruptive database rotation before changing any other product resource.
        # This prevents a failed `--force all` from partially rotating Core/Explorer keys first.
        if force_database and "database" in selected:
            self._validate_database_password_rotation()

        for name in selected:
            anu_initialize_durable_directory(directories[name])

        self._install_deployment_assets()
        if "core" in selected:
            self._initialize_product_directories()
        if "database" in selected:
            self._ensure_database_password(force=force_database)
        if "explorer" in selected:
            self._ensure_explorer_oauth_keys(force=force_secrets)

        profile = self._settings.deployment_profile.lower()
        if profile in {"cloudrun", "aws"}:
            return True

        # The root CA is shared infrastructure across products/components and is therefore never
        # rotated by a product-scoped init force. Missing CA material is still created normally.
        ca = self._pki.ensure_ca(force=False)
        if "core" in selected:
            self._synchronize_core_ca_private_key(ca.private_key)
        self._issue_transport_identities(force=force_pki, component=component)
        return True

    def _install_deployment_assets(self) -> None:
        """Install host-visible files required by Compose bind mounts.

        Compose may execute from inside the installer container while talking to the host Docker
        daemon. Repository-relative bind sources are therefore not visible to Docker. Copy packaged
        deployment assets into ``ANU_HOME`` so direct CLI and installer execution use one host path.
        """

        source = Path(__file__).resolve().parents[1] / "assets"
        if not source.is_dir():
            raise FileNotFoundError(f"Deployment assets directory is missing: {source}")
        self._deployment_assets_destination.mkdir(parents=True, exist_ok=True)
        for asset in source.iterdir():
            if not asset.is_file():
                continue
            destination = self._deployment_assets_destination / asset.name
            shutil.copyfile(asset, destination)
            destination.chmod(asset.stat().st_mode & 0o777)

    def _initialize_product_directories(self) -> None:
        """Create Nebula-specific state directories not part of the generic Utils layout."""

        core = self._topology.core
        (core.data / "mailbox").mkdir(parents=True, exist_ok=True)
        (core.data / "sms-mailbox").mkdir(parents=True, exist_ok=True)

    def _validate_database_password_rotation(self) -> None:
        """Refuse password rotation that would desynchronize an existing PostgreSQL cluster."""

        password_file = self._topology.database.secrets / "service-password"
        password_exists = password_file.is_file() and password_file.stat().st_size > 0
        if password_exists and self._database_has_data():
            raise RuntimeError(
                "Refusing to rotate the database password while durable PostgreSQL data exists. "
                "Use 'anu destroy --component database' for an intentional database reset, then "
                "run init again."
            )

    def _ensure_database_password(self, *, force: bool) -> None:
        """Create or explicitly replace the database service password after safety validation."""

        password_file = self._topology.database.secrets / "service-password"
        password_exists = password_file.is_file() and password_file.stat().st_size > 0
        if force or not password_exists:
            password_file.write_text(secrets.token_urlsafe(36) + "\n", encoding="utf-8")
        password_file.chmod(0o600)
        self._synchronize_database_password(
            source=password_file,
            destination=AgentNebulaDeploymentTopology(self._settings).database_credentials.core_destination,
        )

    @staticmethod
    def _synchronize_database_password(*, source: Path, destination: Path) -> None:
        """Copy the database password into a consumer-owned durable secret location."""

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        destination.chmod(0o600)

    def _synchronize_core_ca_private_key(self, source: Path) -> None:
        """Copy the platform CA key into Core's component-owned security input tree."""

        destination = self._topology.core.secrets / "pki" / "root-ca.key"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        destination.chmod(0o600)

    def _database_has_data(self) -> bool:
        """Return whether PostgreSQL durable storage contains initialized database state."""

        data = self._topology.database.data
        return data.is_dir() and any(data.iterdir())

    def _ensure_explorer_oauth_keys(self, *, force: bool) -> None:
        """Create Explorer OAuth authentication and DPoP keys at standard Utils paths."""

        security = DeploymentSecurityPaths(self._topology.explorer)
        for key in (security.oauth_authentication_key, security.oauth_dpop_key):
            if force or not key.is_file() or key.stat().st_size == 0:
                key.parent.mkdir(parents=True, exist_ok=True)
                self._openssl.run(
                    "ecparam",
                    "-name",
                    "prime256v1",
                    "-genkey",
                    "-noout",
                    "-out",
                    str(key),
                )
            key.chmod(0o600)

    def _issue_transport_identities(self, *, force: bool, component: str | None) -> None:
        """Issue TLS identities using stable public names plus existing local/internal SANs."""

        api_host = self._url_hostname(self._core_settings.public_api_url, "Core public API URL")
        ui_host = self._url_hostname(self._core_settings.public_ui_url, "Core public UI URL")
        postgres_host = self._core_settings.database_host
        identities = {
            "core": (
                self._topology.core,
                "registry.agentnebula.ai",
                ("nebula-core", api_host, ui_host, "registry.agentnebula.ai"),
            ),
            "console": (
                self._topology.console,
                "agentnebula.ai",
                ("nebula-console", ui_host, "agentnebula.ai"),
            ),
            "explorer": (
                self._topology.explorer,
                "explorer.agentnebula.ai",
                ("nebula-explorer", ui_host, "explorer.agentnebula.ai"),
            ),
            "database": (
                self._topology.database,
                postgres_host,
                ("nebula-database", postgres_host),
            ),
        }
        selected = tuple(identities) if component is None else (component,)
        for name in selected:
            identity = identities.get(name)
            if identity is None:
                continue
            directory, common_name, dns_names = identity
            self._pki.ensure_server_identity(
                directory=directory,
                common_name=common_name,
                dns_names=dns_names,
                force=force,
            )

    @staticmethod
    def _url_hostname(value: str, label: str) -> str:
        """Return the hostname from one resolved URL used for local certificate identity."""

        hostname = urlparse(value).hostname
        if not hostname:
            raise ValueError(f"{label} has no hostname: {value}")
        return hostname


class OAuthBootstrapService:
    """Initialize only durable OAuth deployment material on the host.

    Runtime directory creation and generated ``application.conf`` publication intentionally
    belong to the OAuth container, matching the established Explorer deployment lifecycle.
    """

    def __init__(self, environment: Mapping[str, str]) -> None:
        """Resolve Utils-owned settings required for durable OAuth initialization."""

        self._settings = anu_load_settings(environment)
        self._oauth = anu_load_oauth_settings(environment)
        self._topology = OAuthDeploymentTopology(self._settings, self._oauth.instance)
        self._pki = DeploymentLocalPkiService(self._settings)
        self._openssl = OpenSslExecutor()

    def initialize(
        self,
        *,
        force_scope: InitializationForceScope | None,
        component: str | None = None,
    ) -> bool:
        """Create OAuth state and regenerate configuration without touching Core ownership."""

        if component not in {None, "service"}:
            return False
        if force_scope not in {
            None,
            InitializationForceScope.CONFIG,
            InitializationForceScope.PKI,
            InitializationForceScope.ALL,
        }:
            return False

        directory = anu_initialize_durable_directory(self._topology.service)
        force_pki = force_scope in {InitializationForceScope.PKI, InitializationForceScope.ALL}
        force_keys = force_scope is InitializationForceScope.ALL
        profile = self._settings.deployment_profile.lower()
        tls_enabled = self._oauth.tls_enabled and profile not in {"cloudrun", "aws"}
        security = DeploymentSecurityPaths(directory)
        public_hostname = "oauth.agentnebula.ai"
        configured_hostname = urlparse(self._oauth.public_url).hostname
        service_hostname = urlparse(self._oauth.service_url).hostname
        if not configured_hostname:
            raise ValueError(f"OAuth public URL has no hostname: {self._oauth.public_url}")
        if not service_hostname:
            raise ValueError(f"OAuth service URL has no hostname: {self._oauth.service_url}")

        if tls_enabled:
            self._pki.ensure_ca(force=False)
            self._pki.ensure_server_identity(
                directory=directory,
                common_name=public_hostname,
                dns_names=(
                    "nebula-oauth",
                    configured_hostname,
                    service_hostname,
                    public_hostname,
                ),
                force=force_pki,
            )

        private_key = directory.secrets / "oauth" / "signing-private.pem"
        public_key = directory.data / "oauth" / "signing-public.pem"
        verification_dir = directory.data / "oauth" / "verification-keys"
        private_key.parent.mkdir(parents=True, exist_ok=True)
        public_key.parent.mkdir(parents=True, exist_ok=True)
        verification_dir.mkdir(parents=True, exist_ok=True)
        key_id = self._oauth.signing_key_id or f"agent-nebula-{profile}-01"
        if force_keys or not private_key.is_file() or private_key.stat().st_size == 0:
            self._openssl.run(
                "genpkey",
                "-algorithm",
                "RSA",
                "-pkeyopt",
                "rsa_keygen_bits:3072",
                "-out",
                str(private_key),
            )
        self._openssl.run(
            "pkey",
            "-in",
            str(private_key),
            "-pubout",
            "-out",
            str(public_key),
        )
        verification_key = verification_dir / f"{key_id}.pem"
        verification_key.write_bytes(public_key.read_bytes())
        private_key.chmod(0o600)
        public_key.chmod(0o644)
        verification_key.chmod(0o644)

        credentials = AgentNebulaDeploymentTopology(self._settings).database_credentials
        database_password_file = credentials.source
        if not database_password_file.is_file():
            raise RuntimeError(
                "OAuth database password is missing. Initialize Nebula database before OAuth."
            )
        credentials.oauth_destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(database_password_file, credentials.oauth_destination)
        credentials.oauth_destination.chmod(0o600)

        return True


class PolicyBootstrapService:
    """Initialize standalone Policy durable state and render its runtime configuration."""

    def __init__(self, environment: Mapping[str, str]) -> None:
        """Resolve settings for durable Policy initialization."""

        self._settings = anu_load_settings(environment)
        self._policy = anu_load_policy_settings(environment)
        self._topology = PolicyDeploymentTopology(self._settings, self._policy.instance)
        self._pki = DeploymentLocalPkiService(self._settings)

    def initialize(
        self,
        *,
        force_scope: InitializationForceScope | None,
        component: str | None = None,
    ) -> bool:
        """Create missing durable directories and refresh generated Policy configuration."""

        if component not in {None, "service"}:
            return False
        if force_scope not in {
            None,
            InitializationForceScope.CONFIG,
            InitializationForceScope.PKI,
            InitializationForceScope.ALL,
        }:
            return False

        directory = anu_initialize_durable_directory(self._topology.service)
        force_pki = force_scope in {InitializationForceScope.PKI, InitializationForceScope.ALL}
        profile = self._settings.deployment_profile.lower()
        tls_enabled = self._policy.tls_enabled and profile not in {"cloudrun", "aws"}
        security = DeploymentSecurityPaths(directory)
        if tls_enabled:
            self._pki.ensure_ca(force=False)
            public_hostname = "policy.agentnebula.ai"
            service_hostname = urlparse(self._policy.service_url).hostname
            if not service_hostname:
                raise ValueError(f"Policy service URL has no hostname: {self._policy.service_url}")
            self._pki.ensure_server_identity(
                directory=directory,
                common_name=public_hostname,
                dns_names=("nebula-policy", service_hostname, public_hostname),
                force=force_pki,
            )

        # Effective application.conf is container runtime state and is rendered by Policy.
        return True


class StudioBootstrapService:
    """Initialize the current single-container Agent Nebula Studio showcase deployment."""

    def __init__(self, environment: Mapping[str, str]) -> None:
        """Resolve shared settings and compose Studio-specific initialization intent."""

        self._settings = anu_load_settings(environment)
        self._studio_settings = anu_load_studio_settings(environment)
        self._directory = StudioDeploymentTopology(self._settings).showcase
        self._pki = DeploymentLocalPkiService(self._settings)

    def initialize(
        self,
        *,
        force_scope: InitializationForceScope | None,
        component: str | None = None,
    ) -> bool:
        """Initialize Studio and only replace PKI when its force scope permits it."""

        if component not in {None, "studio"}:
            return False
        if force_scope is InitializationForceScope.DATABASE:
            return False
        force_pki = force_scope in {InitializationForceScope.PKI, InitializationForceScope.ALL}
        anu_initialize_durable_directory(self._directory)
        profile = self._settings.deployment_profile.lower()
        if profile in {"cloudrun", "aws"}:
            return True

        # Studio shares the Agent Nebula root CA; Studio PKI force rotates only its TLS identity.
        self._pki.ensure_ca(force=False)
        public_url = self._studio_settings.public_url
        hostname = urlparse(public_url).hostname
        if not hostname:
            raise ValueError(f"Studio public URL has no hostname: {public_url}")

        # Utils owns Studio environment parsing.  ``showcase_sans`` is already a
        # normalized tuple, so deployment composition must consume it directly
        # instead of re-parsing the original comma-separated environment value.
        showcase_sans = self._studio_settings.showcase_sans
        self._pki.ensure_server_identity(
            directory=self._directory,
            common_name=hostname,
            dns_names=("studio-showcase", hostname, *showcase_sans),
            force=force_pki,
        )
        return True


class PlaygroundBootstrapService:
    """Initialize only host-owned durable directories for Playground services."""

    _COMPONENTS = ("container", "backend", "ui")

    def __init__(self, environment: Mapping[str, str]) -> None:
        """Resolve shared settings, Playground settings, durable topology, and local PKI."""

        self._settings = anu_load_settings(environment)
        self._playground_settings = anu_load_playground_settings(environment)
        self._topology = PlaygroundDeploymentTopology(self._settings)
        self._pki = DeploymentLocalPkiService(self._settings)

    def initialize(
        self,
        *,
        force_scope: InitializationForceScope | None,
        component: str | None = None,
    ) -> bool:
        """Create durable roots and local TLS identities without host runtime state."""

        if component is not None and component not in self._COMPONENTS:
            return False
        if force_scope is InitializationForceScope.DATABASE:
            return False

        selected = self._COMPONENTS if component is None else (component,)
        for name in selected:
            directory = getattr(self._topology, name)
            anu_initialize_durable_directory(directory)

        profile = self._settings.deployment_profile.strip().lower()
        if profile in {"cloudrun", "aws"}:
            return True

        force_pki = force_scope in {InitializationForceScope.PKI, InitializationForceScope.ALL}
        self._pki.ensure_ca(force=False)
        public_hostname = "playground.agentnebula.ai"
        configured_hostname = urlparse(self._playground_settings.public_url).hostname
        if not configured_hostname:
            raise ValueError(
                "Playground public URL has no hostname: "
                f"{self._playground_settings.public_url}"
            )

        for name in selected:
            directory = getattr(self._topology, name)
            self._pki.ensure_server_identity(
                directory=directory,
                common_name=public_hostname,
                dns_names=(
                    f"playground-{name}",
                    configured_hostname,
                    public_hostname,
                ),
                force=force_pki,
            )
        return True
