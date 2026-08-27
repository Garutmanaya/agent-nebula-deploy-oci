# Agent Nebula Deploy OCI

Build, publish, and install Agent Nebula on a LOCAL AMD64 host or OCI Ampere ARM64 host while using
the same application lifecycle and GHCR image namespace.

Detailed guides:

- [`docs/SETUP-LOCAL.md`](docs/SETUP-LOCAL.md) — build, install, Cloudflare, upgrade, uninstall.
- [`docs/SETUP-OCI.md`](docs/SETUP-OCI.md) — Terraform, Vault, OCI install, Cloudflare, recovery,
  upgrade, uninstall.

## Image build/publish

Application repositories continue to own Dockerfiles. This repository only orchestrates Buildx.

```bash
make builder
make check IMAGE=all

make amd-build IMAGE=all RELEASE=0.5.0
make amd-push  IMAGE=all RELEASE=0.5.0

make arm-build IMAGE=all RELEASE=0.5.0
make arm-push  IMAGE=all RELEASE=0.5.0
```

Registry ownership is configured once in `config/registry.json`.

## Installation image selection

All installations pull images from GHCR. The operator supplies only a logical `TAG`; `latest` is the
default.

```text
TARGET=local TAG=latest  -> latest-amd64
TARGET=oci   TAG=latest  -> latest-arm64
TARGET=local TAG=0.5.0   -> 0.5.0-amd64
TARGET=oci   TAG=0.5.0   -> 0.5.0-arm64
```

Example:

```bash
make init   TARGET=local PROFILE=local PRODUCT=nebula
make deploy TARGET=local PROFILE=local PRODUCT=nebula
make health TARGET=local PROFILE=local PRODUCT=nebula
```

## OCI Terraform

```text
terraform/
├── bootstrap/       AWS S3 Terraform state
├── infrastructure/  OCI VCN/VM/Vault/key/Instance Principal
└── application/     Agent Nebula lifecycle orchestration over SSH
```

The application deployment has two phases:

```bash
make tf-app-apply PHASE=platform TAG=latest PROFILE=local
# Create/import Explorer and Playground Provider API keys.
make tf-app-apply PHASE=applications TAG=latest PROFILE=local
```

## Cloudflare Tunnel

Cloudflare remains an independent host operation and reuses the proven adapter from
`agent-nebula-deploy`:

```bash
make cloudflare-init   TARGET=local PROFILE=cloudflare
make cloudflare-status TARGET=local PROFILE=cloudflare
```

Use `TARGET=oci` when running the same commands on the OCI host.

## Security/data boundaries

```text
OCI Vault                         authoritative security material
/opt/agent-nebula                 durable application state/cache
/run/agent-nebula                 ephemeral plaintext runtime material
```

On OCI, private keys/passwords/API keys are encrypted on persistent disk. Public certificates are
backed up to Vault but remain readable locally because they are public trust material needed by host
infrastructure. LOCAL uses plaintext durable secrets and the same `/run` runtime projection.

Explorer, Playground and PostgreSQL data remain on the durable local filesystem.
