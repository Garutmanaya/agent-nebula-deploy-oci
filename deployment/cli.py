"""Command-line entry points for deployment-owned filesystem operations.

This module stays intentionally small and delegates all topology and initialization behavior to
object-oriented deployment services. Invoke it with ``python -m deployment.cli`` from the
repository root.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .filesystem import DeploymentFilesystemInitializer
from .topology import AgentNebulaDeploymentTopology


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for durable filesystem initialization."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--home",
        type=Path,
        help="Override ANU_HOME for this initialization run.",
    )
    parser.add_argument(
        "--runtime-home",
        type=Path,
        help="Override ANU_RUNTIME_HOME used only to resolve matching container runtime paths.",
    )
    return parser


def environment_overrides(args: argparse.Namespace) -> dict[str, str]:
    """Create canonical Utils environment overrides from explicit CLI arguments."""

    values = dict(os.environ)
    if args.home is not None:
        values["ANU_HOME"] = str(args.home)
    if args.runtime_home is not None:
        values["ANU_RUNTIME_HOME"] = str(args.runtime_home)
    return values


def main() -> int:
    """Initialize all durable component directories and print the resulting roots."""

    args = build_parser().parse_args()
    topology = AgentNebulaDeploymentTopology.from_environment(environment_overrides(args))
    directories = DeploymentFilesystemInitializer(topology).initialize()
    for directory in directories:
        print(directory.product_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
