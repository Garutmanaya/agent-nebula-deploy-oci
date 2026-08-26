PYTHON ?= python3
WORKSPACE ?= ..
MANIFEST ?= config/images.json
REGISTRY_CONFIG ?= config/registry.json
IMAGE ?= all
RELEASE ?= dev
PLATFORM ?= linux/arm64

PIPELINE = $(PYTHON) scripts/image_pipeline.py
COMMON_ARGS = --manifest $(MANIFEST) --registry-config $(REGISTRY_CONFIG) --workspace $(WORKSPACE)

.PHONY: help builder images registry check arm-build arm-push dry-run test tf-init tf-fmt tf-validate tf-plan tf-apply tf-destroy
help:
	@printf '%s\n' \
	  'builder      - verify/create the Agent Nebula multi-platform buildx builder' \
	  'images       - list configured image builds' \
	  'registry     - show configured image registry/release tags' \
	  'check        - validate selected/all enabled repositories (IMAGE=all)' \
	  'arm-build    - build/load selected/all ARM64 images (IMAGE=all RELEASE=0.1.0)' \
	  'arm-push     - build/push selected/all ARM64 images to configured registry' \
	  'dry-run      - print ARM64 commands without executing them' \
	  'test         - run repository unit tests' \
	  'tf-init      - initialize OCI Terraform root' \
	  'tf-validate  - format-check and validate OCI Terraform' \
	  'tf-plan      - create OCI Terraform execution plan' \
	  'tf-apply     - apply OCI Terraform configuration' \
	  'tf-destroy   - destroy OCI Terraform-managed resources'

builder:
	./scripts/check-builder.sh

images:
	$(PIPELINE) list $(COMMON_ARGS)

registry:
	$(PIPELINE) registry $(COMMON_ARGS) --release $(RELEASE)

check:
	$(PIPELINE) check $(IMAGE) $(COMMON_ARGS)

arm-build:
	$(PIPELINE) build $(IMAGE) $(COMMON_ARGS) --platform $(PLATFORM) --release $(RELEASE) --load

arm-push:
	$(PIPELINE) push $(IMAGE) $(COMMON_ARGS) --platform $(PLATFORM) --release $(RELEASE)

# Backward-compatible alias for the earlier target.
push: arm-push

dry-run:
	$(PIPELINE) build $(IMAGE) $(COMMON_ARGS) --platform $(PLATFORM) --release $(RELEASE) --dry-run

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
