# Agent Nebula Local + OCI Deployment

This repository builds Agent Nebula images and owns the new local/OCI host deployment lifecycle.
Application repositories continue to own their Dockerfiles. The existing `agent-nebula-deploy`
repository remains unchanged and is used only as the proven behavior reference during migration.

All Agent Nebula repositories are expected as siblings:

```text
workspace/
├── agent-nebula-deploy-oci/
├── agent-nebula-core/
├── agent-nebula-explorer/
├── agent-nebula-oauth/
├── agent-nebula-playground/
├── agent-nebula-policy/
├── agent-nebula-policy-sdk/
├── agent-nebula-sdk/
├── agent-nebula-utils/
├── agent-nebula-plugins/
├── agent-nebula-runtime/
└── agent-nebula-connect/
```

## Filesystem contract

Durable state lives below `/opt/agent-nebula`; application runtime material lives only below
`/run/agent-nebula` inside containers.

```text
/opt/agent-nebula/
├── nebula/
│   ├── core/
│   └── console/
├── database/
├── explorer/
├── oauth/
├── policy/
├── playground/
│   ├── container/
│   ├── backend/
│   └── ui/
└── nebula-ca/
```

Database credentials are component-owned:

```text
/opt/agent-nebula/database/secrets/service-password
/opt/agent-nebula/nebula/core/secrets/database/service-password
/opt/agent-nebula/oauth/secrets/database/service-password
```

`database` remains the canonical credential owner. Init synchronizes consumer-owned copies without
making Core and OAuth read another component's filesystem.

## Build images

Verify repositories and builder:

```bash
make builder
make images
make check IMAGE=all
```

Build all local AMD64 images:

```bash
make amd-build IMAGE=all RELEASE=0.5.0
```

Build all OCI ARM64 images:

```bash
make arm-build IMAGE=all RELEASE=0.5.0
```

Push all OCI ARM64 images to the configured GHCR repository:

```bash
make arm-push IMAGE=all RELEASE=0.5.0
```

Push AMD64 images when required:

```bash
make amd-push IMAGE=all RELEASE=0.5.0
```

Local tags use `<release>-amd64`; OCI tags use `<release>-arm64`.

## Configure GHCR

Edit `config/registry.json` once:

```json
{
  "registry": {
    "provider": "ghcr",
    "host": "ghcr.io",
    "namespace": "YOUR_GITHUB_USER_OR_ORG",
    "project": "agent-nebula"
  }
}
```

OCI runtime images resolve to:

```text
ghcr.io/<namespace>/agent-nebula/<image>:<release>-arm64
```

## Initialize application state

Initialize products in dependency order. The same commands are used for local and OCI; only
`TARGET` changes.

Local laptop:

```bash
make init TARGET=local PROFILE=local PRODUCT=policy RELEASE=0.5.0
make init TARGET=local PROFILE=local PRODUCT=nebula RELEASE=0.5.0
make init TARGET=local PROFILE=local PRODUCT=oauth RELEASE=0.5.0
make init TARGET=local PROFILE=local PRODUCT=playground RELEASE=0.5.0
```

OCI host:

```bash
make init TARGET=oci PROFILE=local PRODUCT=policy RELEASE=0.5.0
make init TARGET=oci PROFILE=local PRODUCT=nebula RELEASE=0.5.0
make init TARGET=oci PROFILE=local PRODUCT=oauth RELEASE=0.5.0
make init TARGET=oci PROFILE=local PRODUCT=playground RELEASE=0.5.0
```

`PROFILE=cloudflare` remains supported and will be wired to the independent Cloudflare tunnel
initialization in Step 6.

Force initialization preserves the existing category semantics:

```bash
make init TARGET=local PROFILE=local PRODUCT=nebula FORCE=pki RELEASE=0.5.0
make init TARGET=oci PROFILE=local PRODUCT=oauth FORCE=all RELEASE=0.5.0
```

Supported force values are `config`, `pki`, `database`, and `all`.

## Deploy platform

The Nebula stack preserves the proven dependency order:

```text
Policy -> Database/Core/Migrations -> OAuth -> Console -> Explorer when onboarding key exists
```

Local:

```bash
make deploy TARGET=local PROFILE=local PRODUCT=nebula RELEASE=0.5.0
make health TARGET=local PROFILE=local PRODUCT=nebula RELEASE=0.5.0
```

OCI:

```bash
make deploy TARGET=oci PROFILE=local PRODUCT=nebula RELEASE=0.5.0
make health TARGET=oci PROFILE=local PRODUCT=nebula RELEASE=0.5.0
```

For OCI, Compose pulls the configured GHCR ARM64 release images automatically. Local deployment
uses the locally built AMD64 release images.

## Explorer and Playground

Explorer remains behind the existing operator-created onboarding API-key boundary. After platform
bootstrap and API-key installation:

```bash
make deploy TARGET=local PROFILE=local PRODUCT=nebula COMPONENT=explorer RELEASE=0.5.0
make deploy TARGET=local PROFILE=local PRODUCT=playground RELEASE=0.5.0
```

Use `TARGET=oci` for the OCI host.

## Lifecycle commands

```bash
make deploy   TARGET=local PROFILE=local PRODUCT=nebula RELEASE=0.5.0
make redeploy TARGET=local PROFILE=local PRODUCT=nebula RELEASE=0.5.0
make stop     TARGET=local PROFILE=local PRODUCT=nebula RELEASE=0.5.0
make health   TARGET=local PROFILE=local PRODUCT=nebula RELEASE=0.5.0
make logs     TARGET=local PROFILE=local PRODUCT=nebula RELEASE=0.5.0
```

Use `COMPONENT=<name>` for component-scoped operations.

## Tests

```bash
make test
```

## Terraform

The current OCI Terraform remains under `terraform/oci`. It is not yet the final three-stage
Terraform layout. Terraform state bootstrap, application deployment automation, OCI Vault secret
persistence, and Cloudflare tunnel initialization are later implementation steps.

```bash
make tf-init
make tf-validate
make tf-plan
make tf-apply
```

## Security persistence

LOCAL keeps the existing durable plaintext files under `/opt/agent-nebula` and container entrypoints
copy them to `/run/agent-nebula`.

OCI uses OCI Vault as the authoritative security store. During `make init TARGET=oci`, existing
bootstrap logic runs unchanged, then certs/secrets are uploaded to Vault and the same durable paths
are replaced with AES-256-GCM encrypted cache bytes. Containers receive:

```text
ANU_SECRET_ENCRYPTION=masker-key
ANU_MASKER_KEY_FILE=/run/agent-nebula/masker-key
```

and decrypt durable security files only into their container-local `/run/agent-nebula` runtime.
The stock PostgreSQL container is the only exception: Deploy materializes its required password/TLS
files into host `/run/agent-nebula/database` before Compose starts.

OCI initialization requires these environment values on the VM:

```bash
export ANU_OCI_COMPARTMENT_OCID='ocid1.compartment...'
export ANU_OCI_VAULT_OCID='ocid1.vault...'
export ANU_OCI_VAULT_KEY_OCID='ocid1.key...'
export ANU_OCI_AUTH_MODE='instance_principal'
```

Platform bootstrap remains unchanged:

```bash
make bootstrap TARGET=oci PROFILE=cloudflare PRODUCT=nebula
```

Create Explorer and Playground Provider API keys through Console, then import each value without
placing it in shell history:

```bash
make secret-import TARGET=oci COMPONENT=explorer
make secret-import TARGET=oci COMPONENT=playground
```

For local development, the same commands write the API keys to the existing plaintext durable
secret paths:

```bash
make secret-import TARGET=local COMPONENT=explorer
make secret-import TARGET=local COMPONENT=playground
```
