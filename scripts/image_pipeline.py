#!/usr/bin/env python3
"""Central multi-architecture image build/push orchestration for Agent Nebula.

Application repositories continue to own their Dockerfiles. This repository owns
platform selection, image naming, tags, registry publication, and build-context wiring.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ImageSpec:
    name: str
    repository: str
    image: str
    dockerfile: str
    context: str = "."
    build_contexts: dict[str, str] = field(default_factory=dict)
    enabled: bool = True


def run(command: list[str], *, cwd: Path | None = None, dry_run: bool = False) -> None:
    rendered = " ".join(shlex.quote(part) for part in command)
    if cwd:
        print(f"[{cwd}] $ {rendered}")
    else:
        print(f"$ {rendered}")
    if not dry_run:
        subprocess.run(command, cwd=cwd, check=True)


def load_manifest(path: Path) -> tuple[dict[str, Any], list[ImageSpec]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported images manifest schema_version")
    specs: list[ImageSpec] = []
    for raw in payload.get("images", []):
        specs.append(
            ImageSpec(
                name=raw["name"],
                repository=raw["repository"],
                image=raw["image"],
                dockerfile=raw["dockerfile"],
                context=raw.get("context", "."),
                build_contexts=raw.get("build_contexts", {}),
                enabled=raw.get("enabled", True),
            )
        )
    return payload.get("defaults", {}), specs


def resolve_repo(workspace: Path, spec: ImageSpec) -> Path:
    repo = (workspace / spec.repository).resolve()
    if not repo.is_dir():
        raise FileNotFoundError(f"Repository not found: {repo}")
    dockerfile = repo / spec.dockerfile
    if not dockerfile.is_file():
        raise FileNotFoundError(f"Dockerfile not found for {spec.name}: {dockerfile}")
    return repo


def select(specs: list[ImageSpec], names: list[str]) -> list[ImageSpec]:
    enabled = [spec for spec in specs if spec.enabled]
    if not names:
        return enabled
    wanted = set(names)
    known = {spec.name for spec in specs}
    unknown = wanted - known
    if unknown:
        raise ValueError(f"Unknown image(s): {', '.join(sorted(unknown))}")
    disabled = [spec.name for spec in specs if spec.name in wanted and not spec.enabled]
    if disabled:
        raise ValueError(
            "Requested image(s) are disabled pending Dockerfile verification: "
            + ", ".join(sorted(disabled))
        )
    return [spec for spec in enabled if spec.name in wanted]


def image_ref(registry: str, namespace: str, image: str, tag: str) -> str:
    prefix = registry.rstrip("/")
    ns = namespace.strip("/")
    return f"{prefix}/{ns}/{image}:{tag}" if ns else f"{prefix}/{image}:{tag}"


def build_command(
    *,
    spec: ImageSpec,
    repo: Path,
    workspace: Path,
    image: str,
    platforms: list[str],
    push: bool,
    load: bool,
) -> list[str]:
    command = [
        "docker", "buildx", "build",
        "--platform", ",".join(platforms),
        "--file", spec.dockerfile,
        "--tag", image,
    ]
    for name, relative_path in spec.build_contexts.items():
        context_path = (repo / relative_path).resolve()
        if not context_path.exists():
            raise FileNotFoundError(f"Build context {name!r} not found: {context_path}")
        command.extend(["--build-context", f"{name}={context_path}"])
    if push:
        command.append("--push")
    elif load:
        if len(platforms) != 1:
            raise ValueError("--load supports a single platform in this workflow; use --push for multi-arch")
        command.append("--load")
    command.append(str((repo / spec.context).resolve()))
    return command


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("list", "check", "build", "push"))
    parser.add_argument("images", nargs="*")
    parser.add_argument("--manifest", default="config/images.json")
    parser.add_argument("--workspace", default="..", help="Directory containing sibling Agent Nebula repositories")
    parser.add_argument("--registry", default=os.getenv("AN_OCI_REGISTRY", ""))
    parser.add_argument("--namespace", default=os.getenv("AN_OCI_REGISTRY_NAMESPACE", "agent-nebula"))
    parser.add_argument("--tag", default=os.getenv("AN_IMAGE_TAG"))
    parser.add_argument("--platform", action="append", dest="platforms")
    parser.add_argument("--load", action="store_true", help="Load a single-platform build into local Docker")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest_path = (root / args.manifest).resolve()
    workspace = Path(args.workspace).resolve()
    defaults, specs = load_manifest(manifest_path)

    if args.action == "list":
        for spec in specs:
            state = "enabled" if spec.enabled else "disabled"
            print(f"{spec.name:14} {state:8} {spec.repository}/{spec.dockerfile} -> {spec.image}")
        return 0

    selected = select(specs, args.images)
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
    tag = args.tag or defaults.get("tag", "dev")
    push = args.action == "push"
    if push and not args.registry:
        raise ValueError("--registry or AN_OCI_REGISTRY is required for push")

    for spec in selected:
        repo = resolve_repo(workspace, spec)
        target = (
            image_ref(args.registry, args.namespace, spec.image, tag)
            if push or args.registry
            else f"agent-nebula/{spec.image}:{tag}"
        )
        command = build_command(
            spec=spec,
            repo=repo,
            workspace=workspace,
            image=target,
            platforms=platforms,
            push=push,
            load=args.load,
        )
        run(command, cwd=repo, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
