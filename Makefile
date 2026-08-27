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

PIPELINE = $(PYTHON) scripts/image_pipeline.py
COMMON_ARGS = --manifest $(MANIFEST) --registry-config $(REGISTRY_CONFIG) --workspace $(WORKSPACE)
PYTHON_ENV = PYTHONPATH=$(WORKSPACE)/agent-nebula-utils/src:$$PYTHONPATH
LIFECYCLE = $(PYTHON_ENV) $(PYTHON) -m deploy.lifecycle
LIFECYCLE_ARGS = $(PRODUCT) $(PROFILE) --target $(TARGET) --release $(RELEASE) $(if $(COMPONENT),--component $(COMPONENT),)

.PHONY: help builder images registry check arm-build amd-build arm-push amd-push dry-run-arm dry-run-amd init-layout init deploy redeploy stop health logs destroy test tf-init tf-fmt tf-validate tf-plan tf-apply tf-destroy

help:
	@printf '%s\n' \
	  'Image commands:' \
	  '  builder       Verify/create the multi-platform buildx builder' \
	  '  images        List configured images' \
	  '  registry      Show registry and release tags (ARCH=arm64|amd64)' \
	  '  check         Validate selected images/repositories (IMAGE=all)' \
	  '  arm-build     Build/load ARM64 images locally' \
	  '  amd-build     Build/load AMD64 images locally' \
	  '  arm-push      Build/push ARM64 images to configured registry' \
	  '  amd-push      Build/push AMD64 images to configured registry' \
	  '' \
	  'Application commands:' \
	  '  init          Initialize durable product state and environment' \
	  '  deploy        Start selected product/component' \
	  '  redeploy      Recreate selected product/component' \
	  '  stop          Stop selected product/component' \
	  '  health        Run product/component health checks' \
	  '  logs          Show product/component logs' \
	  '  destroy       Remove selected application state (not OCI infrastructure)' \
	  '' \
	  'Selectors: TARGET=local|oci PROFILE=local|cloudflare PRODUCT=nebula|oauth|policy|playground' \
	  '           COMPONENT=<component> RELEASE=<version> FORCE=config|pki|database|all' \
	  '' \
	  'Terraform commands: tf-init tf-validate tf-plan tf-apply tf-destroy'

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

test:
	$(PYTHON_ENV) $(PYTHON) -m unittest discover -s tests -v

TF_DIR ?= terraform/oci

tf-init:
	terraform -chdir=$(TF_DIR) init

tf-fmt:
	terraform -chdir=$(TF_DIR) fmt -recursive

tf-validate: tf-init
	terraform -chdir=$(TF_DIR) fmt -check -recursive
	terraform -chdir=$(TF_DIR) validate

tf-plan: tf-init
	terraform -chdir=$(TF_DIR) plan

tf-apply: tf-init
	terraform -chdir=$(TF_DIR) apply

tf-destroy: tf-init
	terraform -chdir=$(TF_DIR) destroy
