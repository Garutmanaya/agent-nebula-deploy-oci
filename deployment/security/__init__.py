"""OCI/local durable security persistence for Agent Nebula deployments.

The package keeps application lifecycle code independent from the secret backend. Local deployments
retain plaintext durable files. OCI deployments use OCI Vault as the authoritative store and keep
only authenticated encrypted cache files on persistent VM storage.
"""

from .factory import build_security_persistence_service
from .persistence import OciSecurityPersistenceService, SecurityPersistenceService
from .runtime import HostRuntimeSecurityService
from .vault import OciVaultConfiguration, OciVaultSecretClient

__all__ = [
    "HostRuntimeSecurityService",
    "build_security_persistence_service",
    "OciSecurityPersistenceService",
    "OciVaultConfiguration",
    "OciVaultSecretClient",
    "SecurityPersistenceService",
]
