"""Securely import operator-created API keys into LOCAL or OCI durable secret storage.

The command reads secret input without terminal echo. Local mode preserves the existing plaintext
file model; OCI mode writes the authoritative value to Vault and only authenticated ciphertext to
persistent VM storage.
"""

from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path

from deployment.security import build_security_persistence_service
from deployment.targets import DeploymentTarget
from deployment.topology import AgentNebulaDeploymentTopology


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit secret-import command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("local", "oci"), required=True)
    parser.add_argument("--component", choices=("explorer", "playground"), required=True)
    parser.add_argument("--name", default="onboarding-api-key")
    parser.add_argument("--home", type=Path)
    return parser


def _destination(topology: AgentNebulaDeploymentTopology, component: str, name: str) -> Path:
    """Resolve the existing deployment-owned API-key destination without inventing new paths."""

    directory = topology.explorer if component == "explorer" else topology.playground_container
    return directory.secrets / name


def main() -> int:
    """Read one API key interactively and persist it using the selected deployment target."""

    args = build_parser().parse_args()
    environment = dict(os.environ)
    if args.home is not None:
        environment["ANU_HOME"] = str(args.home)
    topology = AgentNebulaDeploymentTopology.from_environment(environment)
    destination = _destination(topology, args.component, args.name)
    value = getpass.getpass(f"Enter {args.component} {args.name}: ").encode("utf-8")
    if not value:
        raise ValueError("Secret value must not be empty")
    destination.parent.mkdir(parents=True, exist_ok=True)
    target = DeploymentTarget(args.target)
    persistence = build_security_persistence_service(
        target=target,
        topology=topology,
        environment=environment,
    )
    if persistence is None:
        destination.write_bytes(value)
        destination.chmod(0o600)
    else:
        persistence.import_secret(destination=destination, value=value)
    print(f"Imported {args.component}/{args.name} into deployment-owned secret storage.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
