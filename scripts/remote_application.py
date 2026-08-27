#!/usr/bin/env python3
"""Terraform-facing CLI for OCI Agent Nebula application installation."""

from __future__ import annotations

import argparse
from pathlib import Path

from deployment.remote_application import (
    OciRemoteApplicationInstaller,
    RemoteApplicationConfiguration,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit, non-secret Terraform application deployment CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", default="ubuntu")
    parser.add_argument("--identity-file", type=Path, required=True)
    parser.add_argument("--utils-repository", type=Path, required=True)
    parser.add_argument("--tag", default="latest")
    parser.add_argument("--profile", choices=("local", "cloudflare"), default="local")
    parser.add_argument("--phase", choices=("prepare", "platform", "applications"), required=True)
    parser.add_argument("--compartment-ocid", required=True)
    parser.add_argument("--vault-ocid", required=True)
    parser.add_argument("--vault-key-ocid", required=True)
    return parser


def main() -> int:
    """Resolve local repository paths and install the selected application phase on OCI."""

    args = build_parser().parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    utils_repository = args.utils_repository.expanduser()
    if not utils_repository.is_absolute():
        utils_repository = (repository_root / utils_repository).resolve()
    configuration = RemoteApplicationConfiguration(
        host=args.host,
        user=args.user,
        identity_file=args.identity_file,
        repository_root=repository_root,
        utils_repository=utils_repository,
        image_tag=args.tag,
        profile=args.profile,
        phase=args.phase,
        compartment_ocid=args.compartment_ocid,
        vault_ocid=args.vault_ocid,
        vault_key_ocid=args.vault_key_ocid,
    )
    OciRemoteApplicationInstaller(configuration).install()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
