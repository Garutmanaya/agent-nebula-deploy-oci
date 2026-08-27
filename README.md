# Agent Nebula Local + OCI Deployment

This repository builds Agent Nebula images and owns the LOCAL/OCI deployment lifecycle. Application
repositories continue to own their Dockerfiles. The existing `agent-nebula-deploy` repository is not
modified.

## Images

```bash
make builder
make check IMAGE=all
make amd-build IMAGE=all RELEASE=0.5.0
make arm-build IMAGE=all RELEASE=0.5.0
make arm-push IMAGE=all RELEASE=0.5.0
```

Registry destination is configured once in `config/registry.json`.

## Direct LOCAL lifecycle

```bash
make init TARGET=local PROFILE=local PRODUCT=policy RELEASE=0.5.0
make init TARGET=local PROFILE=local PRODUCT=nebula RELEASE=0.5.0
make init TARGET=local PROFILE=local PRODUCT=oauth RELEASE=0.5.0
make deploy TARGET=local PROFILE=local PRODUCT=nebula RELEASE=0.5.0
make health TARGET=local PROFILE=local PRODUCT=nebula RELEASE=0.5.0
```

## OCI security contract

OCI Vault is the authoritative durable security store. `/opt/agent-nebula/.../secrets` contains only
AES-256-GCM encrypted cache bytes. Container/runtime preparation decrypts into `/run/agent-nebula`.
LOCAL keeps plaintext durable files and copies them to the same `/run` runtime paths.

Explorer/Playground/PostgreSQL application data remains on the durable local filesystem; it is not
stored in Vault.

## Terraform Step 5

Terraform is split into three independent roots:

```text
terraform/
├── bootstrap/       AWS S3 Terraform-state bucket
├── infrastructure/  OCI VCN/VM/Vault/key/Dynamic Group/IAM
└── application/     Existing Agent Nebula lifecycle over SSH
```

### 1. Bootstrap Terraform state

```bash
cp terraform/bootstrap/terraform.tfvars.example terraform/bootstrap/terraform.tfvars
make tf-bootstrap-plan
make tf-bootstrap-apply

export TF_STATE_BUCKET="$(terraform -chdir=terraform/bootstrap output -raw state_bucket_name)"
export TF_STATE_REGION="$(terraform -chdir=terraform/bootstrap output -raw state_bucket_region)"
```

### 2. Create OCI infrastructure

```bash
cp terraform/infrastructure/terraform.tfvars.example terraform/infrastructure/terraform.tfvars
make tf-infra-plan
make tf-infra-apply
```

The infrastructure root creates the 2 OCPU / 12 GB A1 VM by default, networking, standard OCI Vault,
software-protected Vault key, and an Instance Principal with Vault access. Docker, `uv`, Python 3.12
support, and OCI CLI are bootstrapped through cloud-init.

### 3. Deploy platform phase

```bash
cp terraform/application/terraform.tfvars.example terraform/application/terraform.tfvars
export GHCR_USER='<github-user-or-org>'
export GHCR_TOKEN='<read-packages-token>'

make tf-app-plan  PHASE=platform RELEASE=0.5.0 PROFILE=local
make tf-app-apply PHASE=platform RELEASE=0.5.0 PROFILE=local
```

The platform phase reuses the existing lifecycle and runs:

```text
Policy init
-> Nebula init
-> OAuth init
-> Policy/Database/Core/OAuth/Console deploy
-> health
-> existing interactive platform-bootstrap
```

`platform-bootstrap` is intentionally unchanged and prompts for the existing platform account
passwords. Provider API keys are still created manually through Console.

The GHCR token is never a Terraform variable. It is piped through SSH to `docker login`, whose
`DOCKER_CONFIG` is placed under `/run/agent-nebula`, then removed after the deployment attempt.

### 4. Import API keys

After platform bootstrap, create Provider API keys in Console. On the OCI VM run:

```bash
cd /opt/agent-nebula/deploy
set -a; . config/oci-runtime.env; set +a

make PYTHON=/opt/agent-nebula/deploy-venv/bin/python \
  WORKSPACE=/opt/agent-nebula/deploy-deps \
  secret-import TARGET=oci COMPONENT=explorer

make PYTHON=/opt/agent-nebula/deploy-venv/bin/python \
  WORKSPACE=/opt/agent-nebula/deploy-deps \
  secret-import TARGET=oci COMPONENT=playground
```

The raw keys go to OCI Vault and only encrypted cache files remain under `/opt`.

### 5. Deploy Explorer and Playground

```bash
export GHCR_TOKEN='<read-packages-token>'
make tf-app-plan  PHASE=applications RELEASE=0.5.0 PROFILE=local
make tf-app-apply PHASE=applications RELEASE=0.5.0 PROFILE=local
```

This initializes/deploys Explorer first, then Playground, with health gates.

## Cloudflare

Cloudflare Tunnel initialization remains an independent deployment concern and is intentionally not
implemented in Step 5. It will be added as Step 6 by copying/reusing the proven Cloudflare behavior
from `agent-nebula-deploy`.
