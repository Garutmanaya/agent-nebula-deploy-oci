# Agent Nebula OCI Deployment

Build and publish Agent Nebula ARM64/AMD64 container images and provision OCI infrastructure.

All Agent Nebula repositories are expected as siblings of this repository.

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

## Configure registry

Edit `config/registry.json`:

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

Remote image names are generated as:

```text
ghcr.io/<github-user-or-org>/agent-nebula/<image>:<tag>
```

Example:

```text
ghcr.io/<github-user-or-org>/agent-nebula/nebula-core:0.5.0-arm64
```

Login to GHCR before pushing:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
```

## Builder

```bash
make builder
make images
make check IMAGE=all
```

## ARM64 builds

Build one image:

```bash
make arm-build IMAGE=policy RELEASE=0.5.0
```

Build all configured images:

```bash
make arm-build IMAGE=all RELEASE=0.5.0
```

Push one image:

```bash
make arm-push IMAGE=policy RELEASE=0.5.0
```

Push all images:

```bash
make arm-push IMAGE=all RELEASE=0.5.0
```

Tags:

```text
<release>-arm64
latest-arm64
```

Local example: `agent-nebula/nebula-core:0.5.0-arm64`.

Remote example: `ghcr.io/<github-user-or-org>/agent-nebula/nebula-core:0.5.0-arm64`.

## AMD64 builds

```bash
make amd-build IMAGE=all RELEASE=0.5.0
make amd-push  IMAGE=all RELEASE=0.5.0
```

Tags:

```text
<release>-amd64
latest-amd64
```

## Configured images

```text
policy
core
console
explorer
oauth
playground-container
playground-backend
playground-ui
```

Use `IMAGE=<name>` for one image or `IMAGE=all` for every enabled image.

## Dry run

```bash
make dry-run-arm IMAGE=all RELEASE=0.5.0
make dry-run-amd IMAGE=all RELEASE=0.5.0
```

## Tests

```bash
make test
```

## OCI Terraform

Terraform files are under `terraform/oci`.

```bash
cp terraform/oci/terraform.tfvars.example terraform/oci/terraform.tfvars
make tf-init
make tf-validate
make tf-plan
make tf-apply
```

Destroy Terraform-managed OCI resources:

```bash
make tf-destroy
```

For the first OCI deployment, validate the manual deployment before recreating the environment with Terraform.
