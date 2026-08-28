"""Tests for OCI Vault authoritative storage and encrypted VM-local cache behavior."""

from __future__ import annotations

from pathlib import Path

from agent_nebula_utils import AesGcmFileCipher, anu_load_settings

from deployment.security.persistence import OciSecurityPersistenceService
from deployment.topology import AgentNebulaDeploymentTopology


class InMemoryVault:
    """Minimal Vault double preserving the production client's byte-oriented contract."""

    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    def put(self, name: str, value: bytes) -> None:
        """Persist one test secret value."""

        self.values[name] = value

    def get(self, name: str) -> bytes | None:
        """Return one test secret value when present."""

        return self.values.get(name)

    def list_names(self) -> tuple[str, ...]:
        """Return deterministic test secret names."""

        return tuple(sorted(self.values))


def _service(tmp_path: Path) -> tuple[OciSecurityPersistenceService, InMemoryVault]:
    """Create a persistence service rooted entirely below the test directory."""

    settings = anu_load_settings(
        {
            "ANU_HOME": str(tmp_path / "opt"),
            "ANU_RUNTIME_HOME": str(tmp_path / "run"),
        }
    )
    topology = AgentNebulaDeploymentTopology(settings)
    vault = InMemoryVault()
    service = OciSecurityPersistenceService(
        topology=topology,
        vault=vault,  # type: ignore[arg-type]
        staging_root=tmp_path / "staging",
    )
    return service, vault


def test_finalize_uploads_plaintext_and_leaves_only_encrypted_cache(tmp_path: Path) -> None:
    """OCI persistence must keep Vault authoritative while eliminating plaintext durable bytes."""

    service, vault = _service(tmp_path)
    secret = service.topology.core.secrets / "database" / "service-password"
    secret.parent.mkdir(parents=True)
    secret.write_bytes(b"database-secret")

    service.finalize_initialization()

    assert secret.read_bytes() != b"database-secret"
    assert AesGcmFileCipher.is_encrypted_bytes(secret.read_bytes())
    assert b"database-secret" in vault.values.values()


def test_prepare_restores_and_unseals_vault_material_for_existing_bootstrap(tmp_path: Path) -> None:
    """Fresh OCI hosts must reconstruct durable material before unchanged init code executes."""

    service, vault = _service(tmp_path)
    destination = service.topology.explorer.secrets / "onboarding-api-key"
    vault.put(service._vault_name(destination), b"explorer-key")

    service.prepare_for_initialization()

    assert destination.read_bytes() == b"explorer-key"


def test_finalize_keeps_public_certificate_readable_while_backing_it_up(tmp_path: Path) -> None:
    """Public certificates remain host-readable for infrastructure while Vault stays authoritative."""

    service, vault = _service(tmp_path)
    certificate = service.topology.core.certs / "server.crt"
    certificate.parent.mkdir(parents=True)
    certificate.write_bytes(b"public-certificate")

    service.finalize_initialization()

    assert certificate.read_bytes() == b"public-certificate"
    assert b"public-certificate" in vault.values.values()


def test_prepare_for_deployment_materializes_plaintext_only_to_staging(tmp_path: Path) -> None:
    """OCI deployment decrypts cache into staging without writing a master-key file."""

    service, _ = _service(tmp_path)
    secret = service.topology.oauth.secrets / "database" / "service-password"
    secret.parent.mkdir(parents=True)
    secret.write_bytes(b"oauth-database-secret")
    service.finalize_initialization()

    staging = service.prepare_for_deployment()
    staged = staging / secret.relative_to(service.topology.settings.home)

    assert staged.read_bytes() == b"oauth-database-secret"
    assert AesGcmFileCipher.is_encrypted_bytes(secret.read_bytes())
    assert not (tmp_path / "run" / "masker-key").exists()
