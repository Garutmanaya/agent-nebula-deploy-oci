#!/usr/bin/env python3
"""Build and publish Agent Nebula images from the shared deployment image configuration."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from deployment.images import (  # noqa: E402
    ImageConfigurationRepository,
    ImageSpec,
    registry_image_reference,
    release_tags,
    select_images,
)


def run(command: list[str], *, cwd: Path | None = None, dry_run: bool = False) -> None:
    """Print and execute one build command unless dry-run mode is selected."""

    rendered = " ".join(shlex.quote(part) for part in command)
    print(f"[{cwd}] $ {rendered}" if cwd else f"$ {rendered}")
    if not dry_run:
        subprocess.run(command, cwd=cwd, check=True)


def resolve_repo(workspace: Path, spec: ImageSpec) -> Path:
    """Resolve and validate the application repository and Dockerfile for one image."""

    repo = (workspace / spec.repository).resolve()
    if not repo.is_dir():
        raise FileNotFoundError(f"Repository not found: {repo}")
    dockerfile = repo / spec.dockerfile
    if not dockerfile.is_file():
        raise FileNotFoundError(f"Dockerfile not found for {spec.name}: {dockerfile}")
    return repo


def build_command(
    *,
    spec: ImageSpec,
    repo: Path,
    images: list[str],
    platforms: list[str],
    push: bool,
    load: bool,
) -> list[str]:
    """Create one Docker Buildx invocation using the application-owned Dockerfile."""

    command = [
        "docker",
        "buildx",
        "build",
        "--platform",
        ",".join(platforms),
        "--file",
        spec.dockerfile,
    ]
    for image in images:
        command.extend(["--tag", image])
    for name, relative_path in spec.build_contexts.items():
        context_path = (repo / relative_path).resolve()
        if not context_path.exists():
            raise FileNotFoundError(f"Build context {name!r} not found: {context_path}")
        command.extend(["--build-context", f"{name}={context_path}"])
    if push:
        command.append("--push")
    elif load:
        if len(platforms) != 1:
            raise ValueError(
                "--load supports a single platform in this workflow; use --push for multi-arch"
            )
        command.append("--load")
    command.append(str((repo / spec.context).resolve()))
    return command


def parse_args() -> argparse.Namespace:
    """Parse image pipeline commands and configuration overrides."""

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("list", "registry", "check", "build", "push"))
    parser.add_argument("images", nargs="*")
    parser.add_argument("--manifest", default="config/images.json")
    parser.add_argument("--registry-config", default="config/registry.json")
    parser.add_argument(
        "--workspace",
        default="..",
        help="Directory containing sibling Agent Nebula repositories",
    )
    parser.add_argument("--registry", default=os.getenv("AN_OCI_REGISTRY"))
    parser.add_argument("--namespace", default=os.getenv("AN_OCI_REGISTRY_NAMESPACE"))
    parser.add_argument("--project", default=os.getenv("AN_OCI_REGISTRY_PROJECT"))
    parser.add_argument("--release", default=os.getenv("AN_RELEASE", "dev"))
    parser.add_argument("--platform", action="append", dest="platforms")
    parser.add_argument("--arch", choices=("arm64", "amd64"), default="arm64")
    parser.add_argument("--load", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Execute one configured image build/publication operation."""

    args = parse_args()
    manifest_path = (REPOSITORY_ROOT / args.manifest).resolve()
    registry_path = (REPOSITORY_ROOT / args.registry_config).resolve()
    workspace = Path(args.workspace).resolve()
    configuration = ImageConfigurationRepository(manifest_path, registry_path)
    defaults, specs = configuration.load_manifest()
    registry_config = configuration.load_registry()

    registry_host = args.registry or registry_config.host
    registry_namespace = args.namespace or registry_config.namespace
    registry_project = args.project or registry_config.project

    if args.action == "list":
        for spec in specs:
            state = "enabled" if spec.enabled else "disabled"
            print(
                f"{spec.name:22} {state:8} "
                f"{spec.repository}/{spec.dockerfile} -> {spec.image}"
            )
        return 0

    if args.action == "registry":
        print(f"provider:  {registry_config.provider}")
        print(f"registry:  {registry_host}")
        print(f"namespace: {registry_namespace}")
        print(f"project:   {registry_project}")
        print(f"arch:      {args.arch}")
        print(f"tags:      {', '.join(release_tags(registry_config, args.release, args.arch))}")
        return 0

    selected = select_images(specs, args.images)
    if not selected:
        raise ValueError("No enabled images selected")

    if args.action == "check":
        for spec in selected:
            repo = resolve_repo(workspace, spec)
            for name, relative_path in spec.build_contexts.items():
                path = (repo / relative_path).resolve()
                if not path.exists():
                    raise FileNotFoundError(f"Build context {name!r} not found: {path}")
            print(f"OK {spec.name}: {repo / spec.dockerfile}")
        return 0

    platforms = args.platforms or defaults.get("platforms", ["linux/arm64"])
    tags = release_tags(registry_config, args.release, args.arch)
    push = args.action == "push"
    if push and registry_namespace.startswith("CHANGE_ME"):
        raise ValueError("Configure registry.namespace in config/registry.json before pushing images")

    for spec in selected:
        repo = resolve_repo(workspace, spec)
        if push:
            targets = [
                registry_image_reference(
                    registry_host,
                    registry_namespace,
                    registry_project,
                    spec.image,
                    tag,
                )
                for tag in tags
            ]
        else:
            targets = [f"agent-nebula/{spec.image}:{tag}" for tag in tags]
        run(
            build_command(
                spec=spec,
                repo=repo,
                images=targets,
                platforms=platforms,
                push=push,
                load=args.load,
            ),
            cwd=repo,
            dry_run=args.dry_run,
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
