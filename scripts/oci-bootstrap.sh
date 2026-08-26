#!/usr/bin/env bash
# Idempotent bootstrap for the manually-created OCI Ubuntu host.
set -euo pipefail

sudo apt-get update
sudo apt-get install -y ca-certificates curl jq

if ! command -v docker >/dev/null 2>&1; then
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

sudo systemctl enable --now docker
sudo usermod -aG docker "${USER}"
sudo install -d -m 0755 /opt/agent-nebula
sudo chown "${USER}:${USER}" /opt/agent-nebula

echo "OCI host bootstrap complete. Re-login if Docker group membership was just added."
