#!/usr/bin/env bash
# Prepare the dedicated Buildx builder used for Agent Nebula multi-architecture images.
set -euo pipefail

BUILDER_NAME="${BUILDER_NAME:-agent-nebula-builder}"
BINFMT_IMAGE="${BINFMT_IMAGE:-tonistiigi/binfmt}"

# Create or select the repository-owned builder without changing application repositories.
ensure_builder() {
  if ! docker buildx inspect "$BUILDER_NAME" >/dev/null 2>&1; then
    docker buildx create --name "$BUILDER_NAME" --driver docker-container --use >/dev/null
  else
    docker buildx use "$BUILDER_NAME"
  fi
  docker buildx inspect "$BUILDER_NAME" --bootstrap
}

# Install ARM64 binfmt support on AMD64 development hosts when BuildKit cannot advertise ARM64.
install_arm64_binfmt() {
  echo "Builder does not advertise linux/arm64; installing binfmt/QEMU support..." >&2
  docker run --privileged --rm "$BINFMT_IMAGE" --install arm64

  # BuildKit discovers emulated platforms at worker startup. Recreate only this dedicated builder
  # after registering binfmt so the worker advertises linux/arm64 immediately.
  docker buildx rm "$BUILDER_NAME" >/dev/null 2>&1 || true
  docker buildx create --name "$BUILDER_NAME" --driver docker-container --use >/dev/null
  docker buildx inspect "$BUILDER_NAME" --bootstrap
}

# Return success when the selected builder currently supports ARM64 builds.
supports_arm64() {
  docker buildx inspect "$BUILDER_NAME" | grep -q 'linux/arm64'
}

ensure_builder
if ! supports_arm64; then
  install_arm64_binfmt
fi

if ! supports_arm64; then
  echo "Builder still does not advertise linux/arm64 after binfmt installation." >&2
  exit 2
fi

printf 'Buildx builder %s is ready for amd64 and arm64 builds.\n' "$BUILDER_NAME"
