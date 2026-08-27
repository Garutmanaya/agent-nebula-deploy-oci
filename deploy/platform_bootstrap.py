#!/usr/bin/env python3
"""Run Core's authoritative platform bootstrap through the deployment contract."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from deploy.environment import DeploymentEnvironmentService
from deployment.targets import DeploymentTarget


def _parse_args() -> argparse.Namespace:
    """Parse the platform bootstrap deployment options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("local", "oci"))
    parser.add_argument("--profile", default="local")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Execute the single Core-owned bootstrap workflow inside the running Core container."""

    args = _parse_args()
    if args.profile not in {"local", "cloudflare"}:
        print("Not Applicable")
        return 0

    root = Path(__file__).resolve().parents[1]
    resolved = DeploymentEnvironmentService(target=DeploymentTarget(args.target)).load(product="nebula", profile=args.profile)
    environment = os.environ.copy()
    environment.update(resolved.values)
    command = [
        "docker",
        "compose",
        "--env-file",
        str(resolved.path),
        "-f",
        str(root / "deploy" / "compose" / "compose.yml"),
        "exec",
        "nebula-core",
        "python",
        "scripts/platform-bootstrap.py",
    ]
    if args.force:
        command.append("--force")
    subprocess.run(command, cwd=root, env=environment, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
