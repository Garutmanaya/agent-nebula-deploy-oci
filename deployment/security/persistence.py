"""Durable OCI security persistence and plaintext host-staging lifecycle.

OCI Vault is authoritative. Persistent VM files remain an authenticated encrypted cache for
private material. Before containers start, this service decrypts required security material into
an ephemeral host staging tree. The masker/master key never leaves process memory.
"""

from __future__ import annotations

import base64
import os
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from agent_nebula_utils import AesGcmFileCipher, anu_ca_paths

from deployment.topology import AgentNebulaDeploymentTopology
from .vault import OciVaultSecretClient


class SecurityPersistenceService(ABC):
    """Define target-specific persistence hooks around initialization and deployment."""

    @abstractmethod
    def prepare_for_deployment(self) -> Path:
        """Prepare and return a plaintext host security source for container deployment."""

    @abstractmethod
    def prepare_for_initialization(self) -> None:
        """Prepare durable files before existing initialization logic executes."""

    @abstractmethod
    def finalize_initialization(self) -> None:
        """Persist and protect security files after existing initialization completes."""

    @abstractmethod
    def import_secret(self, *, destination: Path, value: bytes) -> None:
        """Persist one operator-created secret without exposing it through application APIs."""


@dataclass(slots=True)
class OciSecurityPersistenceService(SecurityPersistenceService):
    """Use OCI Vault as source of truth and encrypted VM-local cache for private material."""

    topology: AgentNebulaDeploymentTopology
    vault: OciVaultSecretClient
    staging_root: Path

    _MASTER_SECRET_NAME = "anu-masker-key"  # Preserve the existing Vault secret name.
    _FILE_SECRET_PREFIX = "anu-file-"

    def prepare_for_deployment(self) -> Path:
        """Restore encrypted cache and materialize plaintext files into ephemeral host staging."""

        cipher = self._cipher()
        self._restore_from_vault(cipher)
        self._prepare_staging_root()
        for path in self._security_files():
            payload = path.read_bytes()
            plaintext = cipher.decrypt(payload) if AesGcmFileCipher.is_encrypted_bytes(payload) else payload
            destination = self.staging_root / path.resolve().relative_to(
                self.topology.settings.home.resolve()
            )
            self._atomic_write(destination, plaintext, mode=self._source_mode(path))
        return self.staging_root

    def prepare_for_initialization(self) -> None:
        """Restore missing Vault material and temporarily unseal cache for bootstrap compatibility."""

        cipher = self._cipher()
        self._restore_from_vault(cipher)
        for path in self._security_files():
            payload = path.read_bytes()
            if AesGcmFileCipher.is_encrypted_bytes(payload):
                self._atomic_write(path, cipher.decrypt(payload), mode=self._source_mode(path))

    def finalize_initialization(self) -> None:
        """Upload security files to Vault and encrypt private material on persistent disk."""

        cipher = self._cipher()
        for path in self._security_files():
            payload = path.read_bytes()
            plaintext = cipher.decrypt(payload) if AesGcmFileCipher.is_encrypted_bytes(payload) else payload
            self.vault.put(self._vault_name(path), plaintext)
            mode = self._source_mode(path)
            cached = cipher.encrypt(plaintext) if mode == 0o600 else plaintext
            self._atomic_write(path, cached, mode=mode)

    def import_secret(self, *, destination: Path, value: bytes) -> None:
        """Store an operator-created API key in Vault and write only encrypted bytes to disk."""

        destination = destination.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.vault.put(self._vault_name(destination), value)
        self._atomic_write(destination, self._cipher().encrypt(value), mode=0o600)

    def _cipher(self) -> AesGcmFileCipher:
        """Return a cipher using the Vault-owned master key held only in process memory."""

        key = self.vault.get(self._MASTER_SECRET_NAME)
        if key is None:
            key = AesGcmFileCipher.generate_key()
            self.vault.put(self._MASTER_SECRET_NAME, key)
        return AesGcmFileCipher(key)

    def _prepare_staging_root(self) -> None:
        """Recreate the plaintext staging root so stale security files cannot survive deployment."""

        root = self.staging_root.expanduser().resolve()
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True, mode=0o700)

    def _restore_from_vault(self, cipher: AesGcmFileCipher) -> None:
        """Recreate encrypted local cache files from Vault on a fresh or rebuilt VM."""

        for name in self.vault.list_names():
            if not name.startswith(self._FILE_SECRET_PREFIX):
                continue
            relative = self._decode_relative_path(name)
            destination = (self.topology.settings.home / relative).resolve()
            if self.topology.settings.home.resolve() not in destination.parents:
                raise ValueError(f"Vault secret resolves outside ANU_HOME: {relative}")
            if destination.exists():
                continue
            value = self.vault.get(name)
            if value is None:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            mode = self._source_mode(destination)
            cached = cipher.encrypt(value) if mode == 0o600 else value
            self._atomic_write(destination, cached, mode=mode)

    def _security_files(self) -> tuple[Path, ...]:
        """Return regular durable secret/certificate files across managed components and CA."""

        roots: list[Path] = []
        directories = (
            self.topology.core,
            self.topology.console,
            self.topology.database,
            self.topology.explorer,
            self.topology.oauth,
            self.topology.policy,
            self.topology.playground_container,
            self.topology.playground_backend,
            self.topology.playground_ui,
        )
        for directory in directories:
            roots.extend((directory.secrets, directory.certs))
        ca = anu_ca_paths(self.topology.settings)
        roots.extend(
            (
                ca.root / self.topology.settings.secrets_dir,
                ca.root / self.topology.settings.certs_dir,
            )
        )
        files: list[Path] = []
        for root in roots:
            if not root.exists():
                continue
            files.extend(path for path in root.rglob("*") if path.is_file() and not path.is_symlink())
        return tuple(sorted(set(path.resolve() for path in files)))

    def _vault_name(self, path: Path) -> str:
        """Encode an ANU_HOME-relative path into a reversible OCI-compatible secret name."""

        relative = path.expanduser().resolve().relative_to(self.topology.settings.home.resolve())
        encoded = base64.b32encode(str(relative).encode("utf-8")).decode("ascii").rstrip("=").lower()
        return self._FILE_SECRET_PREFIX + encoded

    def _decode_relative_path(self, name: str) -> Path:
        """Decode a deterministic Vault secret name back to its durable relative path."""

        encoded = name.removeprefix(self._FILE_SECRET_PREFIX).upper()
        padded = encoded + "=" * ((8 - len(encoded) % 8) % 8)
        return Path(base64.b32decode(padded).decode("utf-8"))

    @staticmethod
    def _source_mode(path: Path) -> int:
        """Classify private material for encryption while keeping public trust material readable."""

        if "secrets" in path.parts or path.suffix.lower() == ".key":
            return 0o600
        return 0o644

    @staticmethod
    def _atomic_write(path: Path, payload: bytes, *, mode: int) -> None:
        """Atomically replace one durable/runtime security file with restrictive permissions."""

        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            temporary.write_bytes(payload)
            temporary.chmod(mode)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
