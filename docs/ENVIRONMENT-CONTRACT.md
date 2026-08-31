# Agent Nebula Local / OCI Environment Contract

This document is generated from the Phase 3 consumer audit for `agent-nebula-utils` and
`agent-nebula-deploy-oci`. It defines the deployment boundary that tests enforce.

## Deployment dimensions

`TARGET` selects the host/image model only:

- `local`: local Linux host, amd64 images, security source under `ANU_HOME`.
- `oci`: OCI Linux VM, arm64 images, security source materialized under
  `/run/agent-nebula-security-staging`.

`PROFILE=cloudflare` is an optional public-interface layer and is valid for either target. It is
not an OCI deployment target. `agent-nebula-deploy-oci` has no CloudRun or Studio deployment
behavior.

## Local versus OCI differences

With the same hostname, profile, image tag, and application configuration, Local and OCI generated
application values are identical except for deployment mechanics:

- `DEPLOY_SECURITY_SOURCE_ROOT`: `ANU_HOME` on Local; runtime security staging on OCI.
- Effective image references: `*-amd64` on Local and `*-arm64` on OCI for products whose image is
  emitted into the generated environment.

OCI Vault identifiers/authentication settings are deployment inputs consumed by the host security
persistence layer. They are not application behavior and are not duplicated into application
settings merely because the target is OCI.

## Cloudflare public interface

Only these public identities are exposed:

| Interface | Canonical application variable | Cloudflare value |
| --- | --- | --- |
| Console | `ANU_CORE_PUBLIC_UI_URL` | `https://agentnebula.ai` |
| Registry | `ANU_CORE_PUBLIC_API_URL` | `https://registry.agentnebula.ai` |
| Console -> Registry | `ANU_CONSOLE_API_URL` | `https://registry.agentnebula.ai` |
| OAuth identity | `ANU_OAUTH_PUBLIC_URL` | `https://oauth.agentnebula.ai` |
| OAuth issuer | `ANU_OAUTH_ISSUER` | `https://oauth.agentnebula.ai` |

`ANU_NEBULA_URL` follows the Registry public identity where it is consumed as an external control
plane URL. `ANU_EXPLORER_ALLOWED_ORIGINS` follows the Console browser origin for CORS.

The Cloudflare adapter additionally consumes deployment-only tunnel settings:

- `ANU_DEPLOY_CLOUDFLARE_TUNNEL_NAME`
- `ANU_DEPLOY_CLOUDFLARE_TUNNEL_ID`
- `ANU_DEPLOY_CLOUDFLARE_CREDENTIALS_SOURCE`
- `ANU_DEPLOY_CLOUDFLARE_SERVICE_USER`
- `ANU_DEPLOY_CLOUDFLARE_SERVICE_GROUP`
- `ANU_DEPLOY_CLOUDFLARE_FRONTEND_ORIGIN_URL`
- `ANU_DEPLOY_CLOUDFLARE_BACKEND_ORIGIN_URL`
- `ANU_DEPLOY_CLOUDFLARE_ORIGIN_SERVER_NAME`

There are no separate `ANU_DEPLOY_PUBLIC_*_HOST` variables. Hostnames are derived from canonical
application public URLs by the Cloudflare adapter.

## Internal-only services

These remain host-internal when Cloudflare is enabled:

- Explorer: `ANU_EXPLORER_PUBLIC_URL=https://<deployment-host>:8001`
- Console Explorer upstream: `ANU_CONSOLE_EXPLORER_URL=https://<deployment-host>:8001`
- Console Playground upstream: `ANU_CONSOLE_PLAYGROUND_URL=http://<deployment-host>:8094`
- Policy: `ANU_POLICY_SERVICE_URL=https://<deployment-host>:8093`
- OAuth service-to-service endpoint: `ANU_OAUTH_SERVICE_URL=https://<deployment-host>:8092`
- OAuth -> Registry control-plane endpoint: internal Registry host endpoint

Cloudflare Tunnel therefore contains exactly three ingress hostnames: Console, Registry, and OAuth.
Explorer and Playground remain reachable to the browser through Console-owned proxy paths rather
than independent public DNS names.

## Environment ownership rules

- Every concrete `ANU_*` token consumed by deploy-OCI must exist in the canonical Utils registry.
- Derived public-host deployment variables are prohibited when an application public URL already
  owns the identity.
- Component-scoped initialization reuses an existing product environment file and cannot
  regenerate unrelated product environment state. If no product environment exists yet, initial
  component setup may create it once.
- CloudRun and Studio deployment behavior are forbidden in deploy-OCI production code.
- Phase 4 will remove CloudRun and Studio vocabulary from Utils and move Studio-owned configuration
  into the Studio client repository; that boundary change is intentionally not part of Phase 3.
