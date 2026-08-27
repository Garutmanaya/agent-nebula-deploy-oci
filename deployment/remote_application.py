"""Remote OCI application installation built on the existing deployment lifecycle.

Terraform owns orchestration only. This module packages the current deployment repository and the
shared Utils dependency, transfers them over SSH, configures non-secret OCI runtime identifiers, and
invokes the same Make/lifecycle commands used for local deployments. Secret values are never passed
through Terraform variables or written to persistent deployment configuration.
"""

from __future__ import annotations

import base64
import json
import os
import shlex
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class CommandRunner(Protocol):
    """Execute local commands and optionally provide stdin to the child process."""

    def run(
        self,
        argv: tuple[str, ...],
        *,
        input_text: str | None = None,
        interactive: bool = False,
    ) -> None:
        """Execute one command and raise when it fails."""


class SubprocessCommandRunner:
    """Production command runner backed by subprocess without invoking a shell."""

    def run(
        self,
        argv: tuple[str, ...],
        *,
        input_text: str | None = None,
        interactive: bool = False,
    ) -> None:
        """Execute one argument vector while preserving an interactive terminal when requested."""

        kwargs: dict[str, object] = {"check": True, "text": True}
        if input_text is not None:
            kwargs["input"] = input_text
        if not interactive:
            kwargs["stdout"] = None
            kwargs["stderr"] = None
        subprocess.run(argv, **kwargs)


@dataclass(frozen=True, slots=True)
class RemoteApplicationConfiguration:
    """Describe one immutable OCI application deployment invocation."""

    host: str
    user: str
    identity_file: Path
    repository_root: Path
    utils_repository: Path
    release: str
    profile: str
    phase: str
    compartment_ocid: str
    vault_ocid: str
    vault_key_ocid: str

    def validate(self) -> None:
        """Validate paths and lifecycle selectors before network operations begin."""

        if self.phase not in {"platform", "applications"}:
            raise ValueError("phase must be platform or applications")
        if self.profile not in {"local", "cloudflare"}:
            raise ValueError("profile must be local or cloudflare")
        if not self.identity_file.expanduser().is_file():
            raise FileNotFoundError(f"SSH private key not found: {self.identity_file}")
        if not (self.repository_root / "Makefile").is_file():
            raise FileNotFoundError(
                f"Agent Nebula OCI deployment repository not found: {self.repository_root}"
            )
        if not (self.utils_repository / "pyproject.toml").is_file():
            raise FileNotFoundError(
                f"Agent Nebula Utils repository not found: {self.utils_repository}"
            )
        for name, value in (
            ("compartment_ocid", self.compartment_ocid),
            ("vault_ocid", self.vault_ocid),
            ("vault_key_ocid", self.vault_key_ocid),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")


class DeploymentBundleBuilder:
    """Create deployment-only source bundles without Git history or Terraform state."""

    _EXCLUDED_NAMES = {
        ".git",
        ".terraform",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
    }

    def create(self, source: Path, destination: Path) -> None:
        """Archive one repository while excluding local state, caches, and credentials."""

        source = source.resolve()
        with tarfile.open(destination, mode="w:gz") as archive:
            for path in sorted(source.rglob("*")):
                relative = path.relative_to(source)
                if self._excluded(relative):
                    continue
                archive.add(path, arcname=relative, recursive=False)

    def _excluded(self, relative: Path) -> bool:
        """Return whether one repository-relative path is unsafe or unnecessary to transfer."""

        if any(part in self._EXCLUDED_NAMES for part in relative.parts):
            return True
        name = relative.name
        return name.endswith(".tfstate") or ".tfstate." in name or name == "terraform.tfvars"


class OciRemoteApplicationInstaller:
    """Install and invoke Agent Nebula on one OCI VM without duplicating lifecycle logic."""

    _REMOTE_DEPLOY_ROOT = Path("/opt/agent-nebula/deploy")
    _REMOTE_DEPENDENCY_ROOT = Path("/opt/agent-nebula/deploy-deps")
    _REMOTE_UTILS_ROOT = _REMOTE_DEPENDENCY_ROOT / "agent-nebula-utils"
    _REMOTE_VENV = Path("/opt/agent-nebula/deploy-venv")
    _REMOTE_ENV = _REMOTE_DEPLOY_ROOT / "config" / "oci-runtime.env"
    _DOCKER_CONFIG = Path("/run/agent-nebula/docker-config")

    def __init__(
        self,
        configuration: RemoteApplicationConfiguration,
        runner: CommandRunner | None = None,
        bundle_builder: DeploymentBundleBuilder | None = None,
    ) -> None:
        """Capture immutable deployment configuration and injectable transport collaborators."""

        configuration.validate()
        self._configuration = configuration
        self._runner = runner or SubprocessCommandRunner()
        self._bundles = bundle_builder or DeploymentBundleBuilder()
        self._registry = self._load_registry_configuration()

    def install(self) -> None:
        """Transfer deployment sources and execute the selected lifecycle phase."""

        self._wait_for_cloud_init()
        self._transfer_sources()
        self._prepare_remote_tooling()
        self._write_remote_environment()
        self._registry_login_if_required()
        try:
            self._run_phase()
        finally:
            self._registry_logout()

    def _wait_for_cloud_init(self) -> None:
        """Wait for Terraform host bootstrap before application installation."""

        self._ssh("sudo cloud-init status --wait", interactive=False)

    def _transfer_sources(self) -> None:
        """Upload only deployment and shared Utils source required by host lifecycle code."""

        self._ssh(
            "sudo mkdir -p /opt/agent-nebula/deploy /opt/agent-nebula/deploy-deps "
            "&& sudo chown -R ubuntu:ubuntu /opt/agent-nebula/deploy /opt/agent-nebula/deploy-deps",
            interactive=False,
        )
        with tempfile.TemporaryDirectory(prefix="agent-nebula-oci-") as directory:
            temporary = Path(directory)
            deploy_bundle = temporary / "deploy.tar.gz"
            utils_bundle = temporary / "utils.tar.gz"
            self._bundles.create(self._configuration.repository_root, deploy_bundle)
            self._bundles.create(self._configuration.utils_repository, utils_bundle)
            self._scp(deploy_bundle, "/tmp/agent-nebula-deploy.tar.gz")
            self._scp(utils_bundle, "/tmp/agent-nebula-utils.tar.gz")
        self._ssh(
            "rm -rf /opt/agent-nebula/deploy/* /opt/agent-nebula/deploy-deps/agent-nebula-utils "
            "&& mkdir -p /opt/agent-nebula/deploy /opt/agent-nebula/deploy-deps/agent-nebula-utils "
            "&& tar -xzf /tmp/agent-nebula-deploy.tar.gz -C /opt/agent-nebula/deploy "
            "&& tar -xzf /tmp/agent-nebula-utils.tar.gz "
            "-C /opt/agent-nebula/deploy-deps/agent-nebula-utils "
            "&& rm -f /tmp/agent-nebula-deploy.tar.gz /tmp/agent-nebula-utils.tar.gz",
            interactive=False,
        )

    def _prepare_remote_tooling(self) -> None:
        """Create the Python 3.12 deployment environment from the shared Utils package."""

        command = (
            f"uv venv --python 3.12 {self._REMOTE_VENV} "
            f"&& uv pip install --python {self._REMOTE_VENV / 'bin/python'} "
            f"{self._REMOTE_UTILS_ROOT}"
        )
        self._ssh(command, interactive=False)

    def _write_remote_environment(self) -> None:
        """Persist only non-secret OCI identifiers required by Vault-backed initialization."""

        values = {
            "ANU_HOME": "/opt/agent-nebula",
            "ANU_RUNTIME_HOME": "/run/agent-nebula",
            "ANU_OCI_COMPARTMENT_OCID": self._configuration.compartment_ocid,
            "ANU_OCI_VAULT_OCID": self._configuration.vault_ocid,
            "ANU_OCI_VAULT_KEY_OCID": self._configuration.vault_key_ocid,
            "ANU_OCI_AUTH_MODE": "instance_principal",
            "ANU_OCI_SECRET_PREFIX": "anu",
            "ANU_MASKER_KEY_FILE": "/run/agent-nebula/masker-key",
        }
        content = "\n".join(f"{key}={shlex.quote(value)}" for key, value in values.items()) + "\n"
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        self._ssh(
            f"mkdir -p {self._REMOTE_ENV.parent} && "
            f"printf %s {shlex.quote(encoded)} | base64 -d > {self._REMOTE_ENV} && "
            f"chmod 600 {self._REMOTE_ENV}",
            interactive=False,
        )

    def _registry_login_if_required(self) -> None:
        """Authenticate to private GHCR using operator environment only; never Terraform state."""

        token = os.environ.get("GHCR_TOKEN", "")
        if not token:
            raise RuntimeError(
                "GHCR_TOKEN is required in the operator shell for private GHCR images. "
                "It is intentionally not accepted as a Terraform variable."
            )
        host = self._registry["host"]
        username = os.environ.get("GHCR_USER") or self._registry["namespace"]
        command = (
            f"mkdir -p {self._DOCKER_CONFIG} && chmod 700 {self._DOCKER_CONFIG} && "
            f"DOCKER_CONFIG={self._DOCKER_CONFIG} docker login {shlex.quote(host)} "
            f"-u {shlex.quote(username)} --password-stdin"
        )
        self._ssh(command, input_text=token + "\n", interactive=False)

    def _registry_logout(self) -> None:
        """Remove temporary GHCR credentials from host tmpfs after each deployment attempt."""

        host = self._registry["host"]
        command = (
            f"DOCKER_CONFIG={self._DOCKER_CONFIG} docker logout {shlex.quote(host)} "
            ">/dev/null 2>&1 || true; "
            f"rm -rf {self._DOCKER_CONFIG}"
        )
        try:
            self._ssh(command, interactive=False)
        except subprocess.CalledProcessError:
            # Deployment failures must remain the primary error; cleanup is best effort.
            pass

    def _run_phase(self) -> None:
        """Invoke the existing Make/lifecycle commands for the selected deployment phase."""

        for command, interactive in self._phase_commands():
            self._ssh(self._remote_make_prefix() + command, interactive=interactive)

    def _phase_commands(self) -> tuple[tuple[str, bool], ...]:
        """Return the exact existing lifecycle commands required for one deployment phase."""

        common = (
            f"TARGET=oci PROFILE={shlex.quote(self._configuration.profile)} "
            f"RELEASE={shlex.quote(self._configuration.release)}"
        )
        make = (
            f"make PYTHON={self._REMOTE_VENV / 'bin/python'} "
            f"WORKSPACE={self._REMOTE_DEPENDENCY_ROOT}"
        )
        if self._configuration.phase == "platform":
            return (
                (f"{make} init {common} PRODUCT=policy", False),
                (f"{make} init {common} PRODUCT=nebula", False),
                (f"{make} init {common} PRODUCT=oauth", False),
                (f"{make} deploy {common} PRODUCT=nebula", False),
                (f"{make} health {common} PRODUCT=nebula", False),
                (f"{make} bootstrap {common} PRODUCT=nebula", True),
            )
        return (
            (f"{make} init {common} PRODUCT=nebula COMPONENT=explorer", False),
            (f"{make} deploy {common} PRODUCT=nebula COMPONENT=explorer", False),
            (f"{make} health {common} PRODUCT=nebula COMPONENT=explorer", False),
            (f"{make} init {common} PRODUCT=playground", False),
            (f"{make} deploy {common} PRODUCT=playground", False),
            (f"{make} health {common} PRODUCT=playground", False),
        )

    def _remote_make_prefix(self) -> str:
        """Return environment preparation shared by every remote lifecycle command."""

        return (
            f"cd {self._REMOTE_DEPLOY_ROOT} && "
            f"set -a && . {self._REMOTE_ENV} && set +a && "
            f"export DOCKER_CONFIG={self._DOCKER_CONFIG} && "
        )

    def _load_registry_configuration(self) -> dict[str, str]:
        """Load the same configured GHCR destination used by the image pipeline."""

        path = self._configuration.repository_root / "config" / "registry.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        registry = payload.get("registry", {})
        required = ("host", "namespace", "project")
        missing = [key for key in required if not str(registry.get(key, "")).strip()]
        if missing:
            raise ValueError("Incomplete registry configuration: " + ", ".join(missing))
        return {key: str(registry[key]) for key in required}

    def _ssh(
        self,
        command: str,
        *,
        input_text: str | None = None,
        interactive: bool,
    ) -> None:
        """Execute one remote command through key-only SSH."""

        argv = [*self._ssh_base()]
        if interactive:
            argv.append("-tt")
        argv.extend((self._remote(), command))
        self._runner.run(tuple(argv), input_text=input_text, interactive=interactive)

    def _scp(self, source: Path, destination: str) -> None:
        """Copy one temporary deployment archive to the OCI VM."""

        argv = (
            "scp",
            "-i",
            str(self._configuration.identity_file.expanduser()),
            "-o",
            "StrictHostKeyChecking=accept-new",
            str(source),
            f"{self._remote()}:{destination}",
        )
        self._runner.run(argv)

    def _ssh_base(self) -> tuple[str, ...]:
        """Return common SSH transport arguments."""

        return (
            "ssh",
            "-i",
            str(self._configuration.identity_file.expanduser()),
            "-o",
            "StrictHostKeyChecking=accept-new",
        )

    def _remote(self) -> str:
        """Return the canonical SSH destination string."""

        return f"{self._configuration.user}@{self._configuration.host}"
