#!/usr/bin/env bash
# Script: deploy/assets/postgres-entrypoint-tls.sh
# Purpose:
#   Prepare PostgreSQL's TLS files with the ownership and permissions required
#   by the official PostgreSQL image, then delegate to its normal entrypoint.
#
#   Deployment-owned certificates are mounted read-only into the same container-local
#   staging path used by the proven pre-Utils deployment. This is not a host-created
#   ANU runtime directory. PostgreSQL cannot use the private key directly from that
#   read-only mount because it enforces strict key ownership, so this wrapper copies
#   the files into PostgreSQL-owned storage before starting the original entrypoint.

set -euo pipefail

readonly TLS_SOURCE_DIR="/run/agent-nebula/database/pki"
readonly TLS_TARGET_DIR="/var/lib/postgresql/tls"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

validate_tls_sources() {
  local required_file
  for required_file in server.crt server.key root-ca.crt; do
    [[ -s "${TLS_SOURCE_DIR}/${required_file}" ]] || \
      fail "Required PostgreSQL TLS file is missing or empty: ${TLS_SOURCE_DIR}/${required_file}"
  done
}

prepare_tls_directory() {
  install -d -m 0700 -o postgres -g postgres "${TLS_TARGET_DIR}"

  install -m 0644 -o postgres -g postgres \
    "${TLS_SOURCE_DIR}/server.crt" \
    "${TLS_TARGET_DIR}/server.crt"

  install -m 0600 -o postgres -g postgres \
    "${TLS_SOURCE_DIR}/server.key" \
    "${TLS_TARGET_DIR}/server.key"

  install -m 0644 -o postgres -g postgres \
    "${TLS_SOURCE_DIR}/root-ca.crt" \
    "${TLS_TARGET_DIR}/root-ca.crt"
}

start_postgresql() {
  exec /usr/local/bin/docker-entrypoint.sh "$@"
}

main() {
  validate_tls_sources
  prepare_tls_directory
  start_postgresql "$@"
}

main "$@"
