#!/usr/bin/env bash
set -euo pipefail
BUILDER_NAME="${BUILDER_NAME:-agent-nebula-builder}"
if ! docker buildx inspect "$BUILDER_NAME" >/dev/null 2>&1; then
  docker buildx create --name "$BUILDER_NAME" --driver docker-container --use
else
  docker buildx use "$BUILDER_NAME"
fi
docker buildx inspect --bootstrap
if ! docker buildx inspect "$BUILDER_NAME" | grep -q 'linux/arm64'; then
  echo "Builder does not advertise linux/arm64. Install binfmt/QEMU first:" >&2
  echo "  docker run --privileged --rm tonistiigi/binfmt --install arm64" >&2
  exit 2
fi
