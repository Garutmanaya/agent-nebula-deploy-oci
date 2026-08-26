PYTHON ?= python3
WORKSPACE ?= ..
MANIFEST ?= config/images.json
REGISTRY_CONFIG ?= config/registry.json
IMAGE ?= all
RELEASE ?= dev

PIPELINE = $(PYTHON) scripts/image_pipeline.py
COMMON_ARGS = --manifest $(MANIFEST) --registry-config $(REGISTRY_CONFIG) --workspace $(WORKSPACE)

.PHONY: help builder images registry check arm-build amd-build arm-push amd-push dry-run-arm dry-run-amd test tf-init tf-fmt tf-validate tf-plan tf-apply tf-destroy

help:
	@printf '%s\n' \
	  'builder       Verify/create the multi-platform buildx builder' \
	  'images        List configured images' \
	  'registry      Show registry and release tags (ARCH=arm64|amd64)' \
	  'check         Validate selected images/repositories (IMAGE=all)' \
	  'arm-build     Build/load ARM64 images locally' \
	  'amd-build     Build/load AMD64 images locally' \
	  'arm-push      Build/push ARM64 images to configured registry' \
	  'amd-push      Build/push AMD64 images to configured registry' \
	  'dry-run-arm   Print ARM64 build commands' \
	  'dry-run-amd   Print AMD64 build commands' \
	  'test          Run unit tests' \
	  'tf-init       Initialize OCI Terraform' \
	  'tf-validate   Validate OCI Terraform' \
	  'tf-plan       Plan OCI Terraform' \
	  'tf-apply      Apply OCI Terraform' \
	  'tf-destroy    Destroy OCI Terraform resources'

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

test:
	$(PYTHON) -m unittest discover -s tests -v

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
