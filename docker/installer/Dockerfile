# Agent Nebula installer image.
#
# Packages the deployment implementation and shared utilities so an installation
# host only needs Docker plus the small agent-nebula-install wrapper repository.
FROM python:3.12-slim-bookworm

ARG DEBIAN_FRONTEND=noninteractive

# Docker CLI/Compose operate against the host Docker socket. Terraform and the
# OCI CLI are included so the existing deployment Makefile remains usable from
# the packaged installer without requiring these tools on the host.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       bash \
       ca-certificates \
       curl \
       gnupg \
       gosu \
       lsb-release \
       make \
       openssl \
       util-linux \
       unzip \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
       | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" \
       > /etc/apt/sources.list.d/docker.list \
    && curl -fsSL https://apt.releases.hashicorp.com/gpg \
       | gpg --dearmor -o /etc/apt/keyrings/hashicorp.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/hashicorp.gpg] https://apt.releases.hashicorp.com $(. /etc/os-release && echo \"$VERSION_CODENAME\") main" \
       > /etc/apt/sources.list.d/hashicorp.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
       docker-ce-cli \
       docker-compose-plugin \
       terraform \
    && rm -rf /var/lib/apt/lists/*

COPY --from=agent_nebula_utils . /workspace/agent-nebula-utils
COPY . /workspace/agent-nebula-deploy-oci

RUN python -m pip install --no-cache-dir /workspace/agent-nebula-utils \
    && python -m pip install --no-cache-dir oci-cli

COPY docker/installer/entrypoint.sh /usr/local/bin/agent-nebula-installer
RUN chmod 0755 /usr/local/bin/agent-nebula-installer

WORKDIR /workspace/agent-nebula-deploy-oci

# Keep the existing Makefile as the public deployment command contract. The
# host-side wrapper invokes this entrypoint with targets such as init/deploy.
ENTRYPOINT ["/usr/local/bin/agent-nebula-installer"]
CMD ["help"]
