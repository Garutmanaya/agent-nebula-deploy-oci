# Agent Nebula OCI Setup

This guide provisions an Oracle Cloud Infrastructure Ampere host and deploys Agent Nebula from GHCR.
Terraform is split into state bootstrap, OCI infrastructure and application orchestration. Cloudflare
Tunnel remains an independent host-infrastructure operation.

## 1. OCI architecture

The default infrastructure target is:

```text
OCI VM.Standard.A1.Flex
  2 OCPU / 12 GB RAM
  Ubuntu 22.04 ARM64
  50 GB boot volume

Cloudflare Tunnel
  public HTTPS/DNS
        │
        ▼
OCI VM
  Docker Compose
  ├── PostgreSQL
  ├── Policy
  ├── OAuth
  ├── Core
  ├── Console
  ├── Explorer
  └── Playground
```

Agent Studio can remain on Cloud Run independently.

## 2. Filesystem contract

Persistent application/data roots:

```text
/opt/agent-nebula/
├── deploy/                           deployed lifecycle source/config
├── deploy-deps/                      deployment-time Utils dependency
├── deploy-venv/                      deployment Python environment
├── nebula/
│   ├── core/
│   └── console/
├── database/                         PostgreSQL persistent data/security cache
├── explorer/                         Explorer persistent sessions/state
├── oauth/
├── policy/
├── playground/                       Playground persistent experiments/state
├── nebula-ca/
└── cloudflare/                       Cloudflare host configuration
```

Ephemeral plaintext runtime material:

```text
/run/agent-nebula/
├── nebula/
├── database/
├── explorer/
├── oauth/
├── policy/
├── playground/
├── nebula-ca/
└── docker-config/                    temporary GHCR login state during deployment
```

OCI Vault is authoritative for generated security material. Private keys, passwords and API keys are
AES-256-GCM encrypted on persistent VM storage. Public certificates/trust material are also backed up
to Vault but remain readable on disk because they are public material required by infrastructure such
as Cloudflare origin verification. Applications consume private material only from `/run`.

Explorer/Playground/PostgreSQL data is ordinary persistent filesystem data and is not stored in Vault.

## 3. Prerequisites on the operator workstation

Install/configure:

- Terraform;
- AWS credentials for the Terraform S3 backend;
- OCI CLI/user configuration for Terraform infrastructure provisioning;
- Docker + Buildx for image publication;
- Python 3;
- SSH key used by the OCI instance;
- GitHub PAT with `read:packages` for deployment and `write:packages` for publishing.

The OCI VM itself is bootstrapped by cloud-init with Docker, Compose, Buildx, `uv`, Python 3.12,
OCI CLI and `cloudflared`.

## 4. Build and publish ARM64 images

From `agent-nebula-deploy-oci`:

```bash
make builder
make check IMAGE=all
make arm-build IMAGE=all RELEASE=0.5.0
```

Authenticate GHCR and publish:

```bash
export GHCR_USER='<github-user-or-org>'
export GHCR_TOKEN='<write-packages-token>'
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin

make arm-push IMAGE=all RELEASE=0.5.0
```

Publishing creates:

```text
0.5.0-arm64
latest-arm64
```

OCI installation accepts only the logical `TAG`; `TAG=latest` is the default and resolves
`latest-arm64`. `TAG=0.5.0` resolves `0.5.0-arm64`.

## 5. Terraform state bootstrap

Copy and edit the bootstrap variables:

```bash
cp terraform/bootstrap/terraform.tfvars.example terraform/bootstrap/terraform.tfvars
```

Create the private/versioned/encrypted S3 state bucket:

```bash
make tf-bootstrap-plan
make tf-bootstrap-apply
```

Export its outputs for the remaining Terraform roots:

```bash
export TF_STATE_BUCKET="$(terraform -chdir=terraform/bootstrap output -raw state_bucket_name)"
export TF_STATE_REGION="$(terraform -chdir=terraform/bootstrap output -raw state_bucket_region)"
```

The state bucket is intentionally protected from accidental destruction.

## 6. Provision OCI infrastructure

Copy and edit:

```bash
cp terraform/infrastructure/terraform.tfvars.example terraform/infrastructure/terraform.tfvars
```

The important defaults are:

```hcl
region                  = "us-ashburn-1"
shape                   = "VM.Standard.A1.Flex"
ocpus                   = 2
memory_gbs              = 12
boot_volume_size_gbs    = 50
ssh_source_cidr         = "0.0.0.0/0"
create_swap             = false
```

Set the tenancy/compartment OCIDs and SSH public-key path, then:

```bash
make tf-infra-validate
make tf-infra-plan
make tf-infra-apply
```

Terraform creates:

- VCN and public subnet;
- Internet Gateway and route;
- SSH-only ingress security rule;
- A1 VM;
- OCI Vault and software-protected key;
- Instance Principal Dynamic Group/IAM policy;
- cloud-init host tooling.

Do not expose Core, OAuth, Policy, Explorer, Playground or PostgreSQL ports through OCI ingress.

## 7. Deploy platform phase

For an OCI deployment that will use Cloudflare, first transfer the deployment bundle and initialize
the `cloudflare` profile without starting services:

```bash
export GHCR_USER='<github-user-or-org>'
export GHCR_TOKEN='<read-packages-token>'
make tf-app-apply PHASE=prepare TAG=latest PROFILE=cloudflare
```

This creates the certificates/configuration needed by the Cloudflare origin adapter and intentionally
stops before Compose deployment. Complete the Cloudflare Tunnel initialization in section 10, then
run the platform phase with `PROFILE=cloudflare`. For a private/non-Cloudflare deployment, skip the
prepare phase and use `PROFILE=local`.

Prepare application variables:

```bash
cp terraform/application/terraform.tfvars.example terraform/application/terraform.tfvars
```

Set the SSH private key path. The image tag defaults to `latest`.

Export a GHCR token containing only `read:packages`:

```bash
export GHCR_USER='<github-user-or-org>'
export GHCR_TOKEN='<read-packages-token>'
```

Plan/apply:

```bash
make tf-app-plan PHASE=platform TAG=latest PROFILE=local
make tf-app-apply PHASE=platform TAG=latest PROFILE=local

# Cloudflare deployment after section 10 tunnel setup:
# make tf-app-plan  PHASE=platform TAG=latest PROFILE=cloudflare
# make tf-app-apply PHASE=platform TAG=latest PROFILE=cloudflare
```

`TAG=latest` can be omitted.

The application module transfers only `agent-nebula-deploy-oci` and `agent-nebula-utils`, logs in to
GHCR using temporary `/run/agent-nebula/docker-config`, and invokes the existing lifecycle remotely.
It performs:

```text
Policy init
Nebula init
OAuth init
Policy / PostgreSQL / Core / OAuth / Console deploy
health gate
interactive platform bootstrap
```

No application source repositories are copied to OCI and all runtime images come from GHCR.

## 8. Platform bootstrap and API keys

The existing platform bootstrap remains unchanged. It creates the platform accounts/providers but
intentionally does not create Provider API keys.

After Phase 1, log in to Console and create Provider API keys for Explorer and Playground. Import them
on the OCI VM through the secure CLI:

```bash
ssh -i ~/.ssh/agent_nebula_oci ubuntu@<OCI_PUBLIC_IP>
cd /opt/agent-nebula/deploy
set -a
. config/oci-runtime.env
set +a

make PYTHON=/opt/agent-nebula/deploy-venv/bin/python \
  WORKSPACE=/opt/agent-nebula/deploy-deps \
  secret-import TARGET=oci COMPONENT=explorer

make PYTHON=/opt/agent-nebula/deploy-venv/bin/python \
  WORKSPACE=/opt/agent-nebula/deploy-deps \
  secret-import TARGET=oci COMPONENT=playground
```

The CLI does not accept the raw key as a command-line argument. It writes the authoritative value to
OCI Vault and leaves only encrypted private material on persistent disk.

## 9. Deploy Explorer and Playground

From the operator workstation:

```bash
export GHCR_TOKEN='<read-packages-token>'
make tf-app-plan PHASE=applications TAG=latest PROFILE=local
make tf-app-apply PHASE=applications TAG=latest PROFILE=local

# Use PROFILE=cloudflare when the platform phase uses Cloudflare.
```

This runs Explorer initialization/deployment/health first, then Playground initialization/deployment/
health.

## 10. Cloudflare Tunnel initialization

Cloudflare host integration is independent from application deployment. The implementation is copied
from the proven `agent-nebula-deploy` adapter and uses the same canonical deployment environment
values. Run `PHASE=prepare PROFILE=cloudflare` from section 7 before this step so the OCI host has the
deployment bundle, profile environment and Agent Nebula CA material.

On the OCI VM, authenticate and create the named tunnel once:

```bash
cloudflared tunnel login
cloudflared tunnel create agent-nebula
```

If the tunnel already exists, make sure its credential JSON is available to the deployment user. The
adapter can resolve the tunnel by name (`agent-nebula` by default) or by
`ANU_DEPLOY_CLOUDFLARE_TUNNEL_ID`.

Route DNS hostnames to the named tunnel. For the standard deployment:

```bash
cloudflared tunnel route dns agent-nebula agentnebula.ai
cloudflared tunnel route dns agent-nebula api.agentnebula.ai
cloudflared tunnel route dns agent-nebula explorer.agentnebula.ai
```

Then configure host integration from `/opt/agent-nebula/deploy`:

```bash
cd /opt/agent-nebula/deploy
set -a
. config/oci-runtime.env
set +a

make PYTHON=/opt/agent-nebula/deploy-venv/bin/python \
  WORKSPACE=/opt/agent-nebula/deploy-deps \
  cloudflare-init TARGET=oci PROFILE=cloudflare
```

After `cloudflare-init`, return to the operator workstation and run the platform phase with
`PROFILE=cloudflare`. Once the platform is healthy/bootstrap is complete, import API keys and run the
applications phase with the same profile.

Verify the tunnel service:

```bash
make PYTHON=/opt/agent-nebula/deploy-venv/bin/python \
  WORKSPACE=/opt/agent-nebula/deploy-deps \
  cloudflare-status TARGET=oci PROFILE=cloudflare
```

The adapter writes:

```text
/opt/agent-nebula/cloudflare/credentials.json
/opt/agent-nebula/cloudflare/config.yml
/etc/systemd/system/cloudflared.service
```

and enables the service for reboot persistence. Application origins remain HTTPS; `cloudflared`
validates the origin certificates using the Agent Nebula root CA.

For custom domains/origins, set the existing `ANU_DEPLOY_CLOUDFLARE_*` environment variables before
`cloudflare-init`; no application code changes are required.

## 11. Verify installation

On the OCI VM:

```bash
docker ps
docker stats --no-stream
free -h
df -h /
systemctl status cloudflared --no-pager
```

From the deployment repository:

```bash
make health TARGET=oci PROFILE=cloudflare PRODUCT=nebula TAG=latest
make health TARGET=oci PROFILE=cloudflare PRODUCT=playground TAG=latest
```

Also verify that private persistent material is not plaintext and that plaintext runtime material
exists only under `/run/agent-nebula` while services are running.

## 12. Upgrade

Publish the next ARM64 release:

```bash
make arm-push IMAGE=all RELEASE=0.5.1
```

Deploy that logical tag:

```bash
make tf-app-apply PHASE=platform TAG=0.5.1 PROFILE=local
make tf-app-apply PHASE=applications TAG=0.5.1 PROFILE=local
```

Cloudflare does not need reconfiguration for normal image upgrades.

## 13. Stop and uninstall OCI application

To stop application containers while preserving VM/data/Vault:

```bash
ssh -i ~/.ssh/agent_nebula_oci ubuntu@<OCI_PUBLIC_IP>
cd /opt/agent-nebula/deploy
set -a; . config/oci-runtime.env; set +a

make PYTHON=/opt/agent-nebula/deploy-venv/bin/python WORKSPACE=/opt/agent-nebula/deploy-deps \
  stop TARGET=oci PROFILE=local PRODUCT=playground
make PYTHON=/opt/agent-nebula/deploy-venv/bin/python WORKSPACE=/opt/agent-nebula/deploy-deps \
  stop TARGET=oci PROFILE=local PRODUCT=nebula
```

Remove Cloudflare host integration without deleting the account-side Cloudflare tunnel object:

```bash
make PYTHON=/opt/agent-nebula/deploy-venv/bin/python WORKSPACE=/opt/agent-nebula/deploy-deps \
  cloudflare-destroy TARGET=oci PROFILE=cloudflare
```

## 14. Destroy OCI infrastructure

Before destroying the VM, back up any PostgreSQL/Explorer/Playground data that must survive. Vault
security material survives only while the Vault resources remain.

For a **VM-only rebuild** that preserves Vault identities/secrets, replace only the compute resource:

```bash
terraform -chdir=terraform/infrastructure apply -replace=oci_core_instance.agent_nebula
```

Then rerun the application phases; initialization restores the encrypted local cache from Vault.

For a **complete uninstall** where Vault recovery is no longer required:

```bash
make tf-infra-destroy
```

A complete infrastructure destroy removes the VM, network and the Vault resources owned by that
state. Back up any required data and security material before performing it.

The S3 Terraform-state bucket is intentionally managed separately and protected against accidental
destruction. Remove it only as a deliberate final administrative action after all OCI/application
state is no longer needed.
