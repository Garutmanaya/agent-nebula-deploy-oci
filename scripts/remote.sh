#!/usr/bin/env bash
set -euo pipefail
: "${OCI_HOST:?OCI_HOST is required, e.g. ubuntu@203.0.113.10}"
OCI_SSH_KEY="${OCI_SSH_KEY:-$HOME/.ssh/agent_nebula_oci}"
exec ssh -i "$OCI_SSH_KEY" -o IdentitiesOnly=yes "$OCI_HOST" "$@"
