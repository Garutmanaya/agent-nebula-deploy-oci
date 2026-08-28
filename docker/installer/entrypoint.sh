#!/usr/bin/env bash
set -euo pipefail

# Start as root only to prepare installer-owned host bind mounts. Drop to the
# invoking operator's UID/GID before running Make while preserving supplementary
# groups supplied by `docker run --group-add` (notably the host Docker socket GID).
host_uid="${ANU_INSTALLER_HOST_UID:-0}"
host_gid="${ANU_INSTALLER_HOST_GID:-0}"
staging_root="${DEPLOY_SECURITY_STAGING_ROOT:-/run/agent-nebula-security-staging}"

if [[ "${host_uid}" != "0" ]]; then
  mkdir -p "${staging_root}"
  chown "${host_uid}:${host_gid}" "${staging_root}"
  exec setpriv \
    --reuid="${host_uid}" \
    --regid="${host_gid}" \
    --keep-groups \
    make "$@"
fi

exec make "$@"
