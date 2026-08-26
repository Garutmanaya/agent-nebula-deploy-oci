# Agent Nebula OCI Deployment

`agent-nebula-deploy-oci` is the OCI-specific build and host-deployment adapter for Agent Nebula.
Application repositories continue to own Dockerfiles. This repository owns cross-platform image
orchestration, registry publication, and OCI host operations.

## Design boundary

Do **not** duplicate ARM Dockerfiles in this repository. A Dockerfile should remain architecture
neutral whenever its dependencies support multiple architectures. OCI build orchestration supplies
`--platform linux/arm64` centrally. A source repository is changed only when its Dockerfile itself
contains architecture-specific logic (for example, a hard-coded `linux-amd64` binary download).

The uploaded Policy Dockerfile is already suitable for this approach: its Python base images and
OPA stage are selected by BuildKit for the requested target architecture, and the Policy SDK is
provided through the existing named build context.

## Expected workspace

All repositories are siblings:

```text
workspace/
├── agent-nebula-core/
├── agent-nebula-explorer/
├── agent-nebula-oauth/
├── agent-nebula-playground/
├── agent-nebula-policy/
├── agent-nebula-policy-sdk/
├── agent-nebula-studio/
├── agent-nebula-deploy/
└── agent-nebula-deploy-oci/
```

`config/images.json` is the authoritative list of image-producing repositories. Policy is enabled
because its exact Dockerfile/build context was verified from the supplied archive. Other known
repositories are listed but deliberately disabled until their Dockerfile paths and build contexts
are inspected; this avoids encoding guessed build contracts.

## ARM build

Prepare Buildx/QEMU once on the amd64 development host:

```bash
# only if binfmt has not already been installed
docker run --privileged --rm tonistiigi/binfmt --install arm64
make builder
```

Validate repository paths:

```bash
make images
make check IMAGE=policy
```

Build and load a local ARM64 Policy image:

```bash
make arm-build IMAGE=policy TAG=dev
```

This produces `agent-nebula/nebula-policy:dev` for `linux/arm64` in the local image store.
The image cannot run natively on an amd64 laptop unless emulation is used; the purpose of `--load`
is inspection/export/testing. Normal OCI publication should use `push`.

## Registry publication

Registry publication is config driven through `config/registry.json`. The default template uses
GitHub Container Registry (GHCR), which is convenient when the Agent Nebula repositories are hosted
on GitHub. Set the GitHub user or organization once:

```json
{
  "registry": {
    "provider": "ghcr",
    "host": "ghcr.io",
    "namespace": "YOUR_GITHUB_USER_OR_ORG"
  }
}
```

Authenticate Docker once before pushing. Use a GitHub token with package write permission and never
store the token in this repository:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
```

Inspect the configured destination and generated tags:

```bash
make registry RELEASE=0.5.0
```

A release produces explicit ARM64 tags such as:

```text
ghcr.io/<namespace>/nebula-policy:0.5.0-arm64
ghcr.io/<namespace>/nebula-policy:latest-arm64
```

Build one image locally:

```bash
make arm-build IMAGE=policy RELEASE=0.5.0
```

Build and push one image to the configured registry:

```bash
make arm-push IMAGE=policy RELEASE=0.5.0
```

Build or push every **enabled** image in `config/images.json`:

```bash
make arm-build IMAGE=all RELEASE=0.5.0
make arm-push  IMAGE=all RELEASE=0.5.0
```

`IMAGE=all` intentionally processes enabled entries only. Repositories stay disabled until their
Dockerfile path and required sibling build contexts have been verified. This prevents a bulk release
from silently building an incorrect contract.

CLI/environment overrides for registry host and namespace remain available for CI, but normal local
operation should use the checked-in registry config. Registry credentials are never stored in the
config file.

## OCI host bootstrap

The manually created Ubuntu ARM64 VM can be prepared with:

```bash
./scripts/oci-bootstrap.sh
```

The current manual deployment remains the reference. A matching Terraform root now lives under
`terraform/oci/`. We will continue validating the runtime manually first, then destroy the prototype
and use this Terraform configuration to prove clean recreation from infrastructure-as-code.

```bash
cp terraform/oci/terraform.tfvars.example terraform/oci/terraform.tfvars
make tf-init
make tf-validate
make tf-plan
# after manual validation is complete:
make tf-apply
```

Terraform owns the OCI VCN, subnet, Internet Gateway, route/security rules, A1 VM and cloud-init host
bootstrap. It does not own Agent Nebula Docker containers; those remain in the image/deployment
pipeline.

## Why ARM is centralized here

Centralization avoids adding OCI-specific Make targets to every application repository. The source
repository remains responsible for producing a correct container image. This repository decides
which architecture, registry, tag, and collection of images constitutes an OCI release.

If a Dockerfile downloads a CPU-specific artifact directly, that is a source-image correctness
issue and must be fixed in that source repository using BuildKit `TARGETARCH`/`TARGETOS`; it should
not be patched around from this deployment repository.
