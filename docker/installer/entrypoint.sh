#!/usr/bin/env bash
set -euo pipefail

# Start as root only to make an OCI staging bind mount writable by the invoking
# operator. Run the deployment command itself with the operator's UID/GID so
# durable files retain the same ownership as native execution.
host_uid="${ANU_INSTALLER_HOST_UID:-0}"
host_gid="${ANU_INSTALLER_HOST_GID:-0}"
staging_root="${DEPLOY_SECURITY_STAGING_ROOT:-/run/agent-nebula-security-staging}"

if [[ "${host_uid}" != "0" ]]; then
  mkdir -p "${staging_root}"
  chown "${host_uid}:${host_gid}" "${staging_root}"
  exec gosu "${host_uid}:${host_gid}" make "$@"
fi

exec make "$@"
