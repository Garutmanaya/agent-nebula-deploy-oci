PYTHON ?= python3
WORKSPACE ?= ..
MANIFEST ?= config/images.json
REGISTRY_CONFIG ?= config/registry.json
IMAGE ?= all
RELEASE ?= dev

TARGET ?= local
PROFILE ?= local
PRODUCT ?= nebula
COMPONENT ?=
FORCE ?=
PHASE ?= platform

PIPELINE = $(PYTHON) scripts/image_pipeline.py
COMMON_ARGS = --manifest $(MANIFEST) --registry-config $(REGISTRY_CONFIG) --workspace $(WORKSPACE)
PYTHON_ENV = PYTHONPATH=$(WORKSPACE)/agent-nebula-utils/src:$$PYTHONPATH
LIFECYCLE = $(PYTHON_ENV) $(PYTHON) -m deploy.lifecycle
LIFECYCLE_ARGS = $(PRODUCT) $(PROFILE) --target $(TARGET) --release $(RELEASE) $(if $(COMPONENT),--component $(COMPONENT),)

TF_STATE_BUCKET ?=
TF_STATE_REGION ?= us-east-1
TF_BOOTSTRAP_DIR := terraform/bootstrap
TF_INFRA_DIR := terraform/infrastructure
TF_APP_DIR := terraform/application
TF_INFRA_STATE_KEY := oci/infrastructure/terraform.tfstate
TF_APP_STATE_KEY := oci/application/terraform.tfstate

.PHONY: help builder images registry check arm-build amd-build arm-push amd-push dry-run-arm dry-run-amd init-layout init deploy redeploy stop health logs destroy bootstrap secret-import test \
        tf-bootstrap-init tf-bootstrap-fmt tf-bootstrap-validate tf-bootstrap-plan tf-bootstrap-apply \
        tf-infra-init tf-infra-fmt tf-infra-validate tf-infra-plan tf-infra-apply tf-infra-destroy \
        tf-app-init tf-app-fmt tf-app-validate tf-app-plan tf-app-apply

help:
	@printf '%s\n' \
	  'Image commands:' \
	  '  builder / images / check' \
	  '  arm-build / arm-push     IMAGE=all RELEASE=0.5.0' \
	  '  amd-build / amd-push     IMAGE=all RELEASE=0.5.0' \
	  '' \
	  'Application commands:' \
	  '  init deploy redeploy stop health logs destroy bootstrap secret-import' \
	  '  Selectors: TARGET=local|oci PROFILE=local|cloudflare PRODUCT=nebula|oauth|policy|playground' \
	  '' \
	  'Terraform Step 5:' \
	  '  tf-bootstrap-*  Create the AWS S3 state backend' \
	  '  tf-infra-*      Create OCI network/VM/Vault/Instance Principal' \
	  '  tf-app-*        Deploy PHASE=platform|applications to OCI' \
	  '  Required backend env: TF_STATE_BUCKET=<bucket> TF_STATE_REGION=<region>'

builder:
	./scripts/check-builder.sh

images:
	$(PIPELINE) list $(COMMON_ARGS)

registry:
	$(PIPELINE) registry $(COMMON_ARGS) --release $(RELEASE) --arch $(or $(ARCH),arm64)

check:
	$(PIPELINE) check $(IMAGE) $(COMMON_ARGS)

arm-build:
	$(PIPELINE) build $(IMAGE) $(COMMON_ARGS) --platform linux/arm64 --arch arm64 --release $(RELEASE) --load

amd-build:
	$(PIPELINE) build $(IMAGE) $(COMMON_ARGS) --platform linux/amd64 --arch amd64 --release $(RELEASE) --load

arm-push:
	$(PIPELINE) push $(IMAGE) $(COMMON_ARGS) --platform linux/arm64 --arch arm64 --release $(RELEASE)

amd-push:
	$(PIPELINE) push $(IMAGE) $(COMMON_ARGS) --platform linux/amd64 --arch amd64 --release $(RELEASE)

dry-run-arm:
	$(PIPELINE) build $(IMAGE) $(COMMON_ARGS) --platform linux/arm64 --arch arm64 --release $(RELEASE) --dry-run

dry-run-amd:
	$(PIPELINE) build $(IMAGE) $(COMMON_ARGS) --platform linux/amd64 --arch amd64 --release $(RELEASE) --dry-run

init-layout:
	$(PYTHON_ENV) $(PYTHON) -m deployment.cli

init:
	$(LIFECYCLE) init $(LIFECYCLE_ARGS) $(if $(FORCE),--force $(FORCE),)

deploy:
	$(LIFECYCLE) deploy $(LIFECYCLE_ARGS)

redeploy:
	$(LIFECYCLE) redeploy $(LIFECYCLE_ARGS)

stop:
	$(LIFECYCLE) stop $(LIFECYCLE_ARGS)

health:
	$(LIFECYCLE) health $(LIFECYCLE_ARGS)

logs:
	$(LIFECYCLE) logs $(LIFECYCLE_ARGS)

destroy:
	$(LIFECYCLE) destroy $(LIFECYCLE_ARGS)

bootstrap:
	$(PYTHON_ENV) $(PYTHON) -m deploy.platform_bootstrap $(TARGET) --profile $(PROFILE) $(if $(filter 1 true yes,$(FORCE)),--force,)

secret-import:
	$(PYTHON_ENV) $(PYTHON) -m deployment.security.cli --target $(TARGET) --component $(COMPONENT) --name $(or $(SECRET_NAME),onboarding-api-key)

test:
	$(PYTHON_ENV) $(PYTHON) -m unittest discover -s tests -v

# Terraform state bootstrap is intentionally local-state only.
tf-bootstrap-init:
	terraform -chdir=$(TF_BOOTSTRAP_DIR) init

tf-bootstrap-fmt:
	terraform -chdir=$(TF_BOOTSTRAP_DIR) fmt -recursive

tf-bootstrap-validate: tf-bootstrap-init
	terraform -chdir=$(TF_BOOTSTRAP_DIR) fmt -check -recursive
	terraform -chdir=$(TF_BOOTSTRAP_DIR) validate

tf-bootstrap-plan: tf-bootstrap-init
	terraform -chdir=$(TF_BOOTSTRAP_DIR) plan

tf-bootstrap-apply: tf-bootstrap-init
	terraform -chdir=$(TF_BOOTSTRAP_DIR) apply

# OCI infrastructure and application roots share the S3 bucket but use independent state keys.
tf-infra-init:
	@test -n "$(TF_STATE_BUCKET)" || (echo 'TF_STATE_BUCKET is required' >&2; exit 2)
	terraform -chdir=$(TF_INFRA_DIR) init -reconfigure \
	  -backend-config="bucket=$(TF_STATE_BUCKET)" \
	  -backend-config="key=$(TF_INFRA_STATE_KEY)" \
	  -backend-config="region=$(TF_STATE_REGION)" \
	  -backend-config="encrypt=true"

tf-infra-fmt:
	terraform -chdir=$(TF_INFRA_DIR) fmt -recursive

tf-infra-validate: tf-infra-init
	terraform -chdir=$(TF_INFRA_DIR) fmt -check -recursive
	terraform -chdir=$(TF_INFRA_DIR) validate

tf-infra-plan: tf-infra-init
	terraform -chdir=$(TF_INFRA_DIR) plan

tf-infra-apply: tf-infra-init
	terraform -chdir=$(TF_INFRA_DIR) apply

tf-infra-destroy: tf-infra-init
	terraform -chdir=$(TF_INFRA_DIR) destroy

tf-app-init:
	@test -n "$(TF_STATE_BUCKET)" || (echo 'TF_STATE_BUCKET is required' >&2; exit 2)
	terraform -chdir=$(TF_APP_DIR) init -reconfigure \
	  -backend-config="bucket=$(TF_STATE_BUCKET)" \
	  -backend-config="key=$(TF_APP_STATE_KEY)" \
	  -backend-config="region=$(TF_STATE_REGION)" \
	  -backend-config="encrypt=true"

tf-app-fmt:
	terraform -chdir=$(TF_APP_DIR) fmt -recursive

tf-app-validate: tf-app-init
	TF_VAR_state_bucket=$(TF_STATE_BUCKET) TF_VAR_state_region=$(TF_STATE_REGION) \
	  terraform -chdir=$(TF_APP_DIR) fmt -check -recursive
	TF_VAR_state_bucket=$(TF_STATE_BUCKET) TF_VAR_state_region=$(TF_STATE_REGION) \
	  terraform -chdir=$(TF_APP_DIR) validate

tf-app-plan: tf-app-init
	TF_VAR_state_bucket=$(TF_STATE_BUCKET) TF_VAR_state_region=$(TF_STATE_REGION) \
	  terraform -chdir=$(TF_APP_DIR) plan \
	  -var="release=$(RELEASE)" -var="profile=$(PROFILE)" -var="deployment_phase=$(PHASE)"

tf-app-apply: tf-app-init
	TF_VAR_state_bucket=$(TF_STATE_BUCKET) TF_VAR_state_region=$(TF_STATE_REGION) \
	  terraform -chdir=$(TF_APP_DIR) apply \
	  -var="release=$(RELEASE)" -var="profile=$(PROFILE)" -var="deployment_phase=$(PHASE)"
