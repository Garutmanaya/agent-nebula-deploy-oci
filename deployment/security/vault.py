"""OCI Vault adapter implemented through the OCI CLI and instance-principal authentication.

Using the CLI keeps OCI SDK dependencies out of Agent Nebula application packages. The adapter is
fully injectable for tests and confines all Oracle-specific behavior to the OCI deployment repo.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


_MAX_SECRET_BYTES = 25 * 1024


class CommandRunner(Protocol):
    """Execute one command and return captured stdout."""

    def run(self, argv: tuple[str, ...]) -> str:
        """Execute the supplied argument vector synchronously."""


class SubprocessCommandRunner:
    """Production command runner backed by subprocess without invoking a shell."""

    def run(self, argv: tuple[str, ...]) -> str:
        """Run one OCI CLI command and return UTF-8 stdout."""

        completed = subprocess.run(argv, check=True, capture_output=True, text=True)
        return completed.stdout


@dataclass(frozen=True, slots=True)
class OciVaultConfiguration:
    """OCI identifiers required to create, update, and retrieve Agent Nebula secrets."""

    compartment_ocid: str
    vault_ocid: str
    key_ocid: str
    auth_mode: str = "instance_principal"
    secret_prefix: str = "anu"

    def validate(self) -> None:
        """Fail clearly when required OCI identifiers are absent."""

        missing = [
            name
            for name, value in (
                ("compartment_ocid", self.compartment_ocid),
                ("vault_ocid", self.vault_ocid),
                ("key_ocid", self.key_ocid),
            )
            if not value.strip()
        ]
        if missing:
            raise ValueError("Missing OCI Vault configuration: " + ", ".join(missing))


class OciVaultSecretClient:
    """Store arbitrary Agent Nebula bytes as versioned OCI Vault secrets."""

    def __init__(
        self,
        configuration: OciVaultConfiguration,
        runner: CommandRunner | None = None,
    ) -> None:
        """Create the client with explicit OCI configuration and an injectable command runner."""

        configuration.validate()
        self._configuration = configuration
        self._runner = runner or SubprocessCommandRunner()

    def put(self, name: str, value: bytes) -> None:
        """Create a secret when absent or publish a new CURRENT version when it already exists."""

        if len(value) > _MAX_SECRET_BYTES:
            raise ValueError(
                f"OCI Vault secret {name!r} exceeds the 25 KB secret-bundle limit"
            )
        secret_id = self._secret_id(name)
        if secret_id is not None and self._get_by_name(name) == value:
            return
        content = base64.b64encode(value).decode("ascii")
        if secret_id is None:
            self._run_sensitive_json(
                ("vault", "secret", "create-base64"),
                {
                    "compartmentId": self._configuration.compartment_ocid,
                    "secretName": name,
                    "vaultId": self._configuration.vault_ocid,
                    "keyId": self._configuration.key_ocid,
                    "secretContentContent": content,
                    "secretContentName": "agent-nebula",
                    "secretContentStage": "CURRENT",
                },
            )
            return
        self._run_sensitive_json(
            ("vault", "secret", "update-base64"),
            {
                "secretId": secret_id,
                "secretContentContent": content,
                "secretContentName": "agent-nebula",
                "secretContentStage": "CURRENT",
            },
        )

    def get(self, name: str) -> bytes | None:
        """Return CURRENT secret bytes by name, or ``None`` when the secret does not exist."""

        if self._secret_id(name) is None:
            return None
        return self._get_by_name(name)

    def _get_by_name(self, name: str) -> bytes:
        """Retrieve one known CURRENT secret value without another metadata lookup."""

        output = self._runner.run(
            self._base_command(
                "secrets",
                "secret-bundle",
                "get-secret-bundle-by-name",
                "--secret-name",
                name,
                "--vault-id",
                self._configuration.vault_ocid,
                "--stage",
                "CURRENT",
            )
        )
        payload = json.loads(output)
        content = payload["data"]["secret-bundle-content"]["content"]
        return base64.b64decode(content)

    def list_names(self) -> tuple[str, ...]:
        """List active secret names in this Vault using the configured Agent Nebula prefix."""

        output = self._runner.run(
            self._base_command(
                "vault",
                "secret",
                "list",
                "--compartment-id",
                self._configuration.compartment_ocid,
                "--vault-id",
                self._configuration.vault_ocid,
                "--all",
            )
        )
        payload = json.loads(output)
        prefix = f"{self._configuration.secret_prefix}-"
        names = []
        for item in payload.get("data", []):
            name = item.get("secret-name") or item.get("name")
            if isinstance(name, str) and name.startswith(prefix):
                names.append(name)
        return tuple(sorted(set(names)))

    def _secret_id(self, name: str) -> str | None:
        """Resolve one secret OCID by name from OCI Vault metadata."""

        output = self._runner.run(
            self._base_command(
                "vault",
                "secret",
                "list",
                "--compartment-id",
                self._configuration.compartment_ocid,
                "--vault-id",
                self._configuration.vault_ocid,
                "--name",
                name,
                "--all",
            )
        )
        payload = json.loads(output)
        for item in payload.get("data", []):
            item_name = item.get("secret-name") or item.get("name")
            if item_name == name:
                return item.get("id")
        return None

    def _run_sensitive_json(self, command: tuple[str, ...], payload: dict[str, str]) -> None:
        """Pass secret content through a private tmpfs JSON file, never process arguments."""

        runtime_root = Path(os.environ.get("ANU_RUNTIME_HOME", "/run/agent-nebula"))
        directory = runtime_root / ".oci-cli"
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix="vault-", suffix=".json", dir=directory
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(0o600)
            self._runner.run(
                self._base_command(*command, "--from-json", f"file://{temporary}")
            )
        finally:
            temporary.unlink(missing_ok=True)

    def _base_command(self, *arguments: str) -> tuple[str, ...]:
        """Build one OCI CLI command with the configured authentication mode."""

        return ("oci", *arguments, "--auth", self._configuration.auth_mode)
