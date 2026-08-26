PYTHON ?= python3
WORKSPACE ?= ..
MANIFEST ?= config/images.json
IMAGE ?=
TAG ?= dev
PLATFORM ?= linux/arm64
REGISTRY ?=
NAMESPACE ?= agent-nebula
IMAGE_ARGS = $(if $(IMAGE),$(IMAGE),)
REGISTRY_ARG = $(if $(REGISTRY),--registry $(REGISTRY),)

.PHONY: help builder images check arm-build multi-build push dry-run test
help:
	@printf '%s\n' \
	  'builder      - verify/create the Agent Nebula multi-platform buildx builder' \
	  'images       - list configured image builds' \
	  'check        - validate configured repository/Dockerfile/build-context paths' \
	  'arm-build    - build selected/all enabled ARM64 images (IMAGE=policy)' \
	  'multi-build  - build amd64+arm64; requires registry push, use make push-multi manually' \
	  'push         - build and push ARM64 images to REGISTRY' \
	  'dry-run      - print ARM64 build commands without executing them' \
	  'test         - run repository unit tests'

builder:
	./scripts/check-builder.sh

images:
	$(PYTHON) scripts/image_pipeline.py list --manifest $(MANIFEST)

check:
	$(PYTHON) scripts/image_pipeline.py check $(IMAGE_ARGS) --manifest $(MANIFEST) --workspace $(WORKSPACE)

arm-build:
	$(PYTHON) scripts/image_pipeline.py build $(IMAGE_ARGS) --manifest $(MANIFEST) --workspace $(WORKSPACE) --platform $(PLATFORM) --tag $(TAG) --load

push:
	$(PYTHON) scripts/image_pipeline.py push $(IMAGE_ARGS) --manifest $(MANIFEST) --workspace $(WORKSPACE) --platform $(PLATFORM) --tag $(TAG) --registry $(REGISTRY) --namespace $(NAMESPACE)

multi-build:
	@echo 'Use: $(PYTHON) scripts/image_pipeline.py push $(IMAGE_ARGS) --workspace $(WORKSPACE) --registry <registry> --platform linux/amd64 --platform linux/arm64 --tag $(TAG)'

dry-run:
	$(PYTHON) scripts/image_pipeline.py build $(IMAGE_ARGS) --manifest $(MANIFEST) --workspace $(WORKSPACE) --platform $(PLATFORM) --tag $(TAG) --dry-run

test:
	$(PYTHON) -m unittest discover -s tests -v
