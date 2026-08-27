# OCI Application Deployment

This Terraform root orchestrates the existing `agent-nebula-deploy-oci` lifecycle over SSH. It does
not reimplement initialization, Compose ordering, platform bootstrap, Cloudflare host integration or
health logic. Runtime images always come from the GHCR destination in `config/registry.json`.

`image_tag` defaults to `latest`; the OCI target resolves it to `latest-arm64`.

The supported deployment phases are:

```text
prepare
  initialize Policy/Nebula/OAuth profile material only
  used before independent Cloudflare Tunnel setup

platform
  initialize Policy/Nebula/OAuth
  deploy Policy/Database/Core/OAuth/Console
  health
  existing interactive platform-bootstrap

applications
  initialize/deploy/health Explorer
  initialize/deploy/health Playground
```

For Cloudflare, run `prepare` with `profile = "cloudflare"`, configure the named tunnel independently,
then run `platform` and `applications` using the same profile.

The bootstrap intentionally remains interactive and unchanged. After bootstrap, create Explorer and
Playground Provider API keys in Console and import them on the VM using the secure secret-import CLI.

Private GHCR packages require `GHCR_TOKEN` in the operator shell when Terraform applies. The token is
piped over SSH to Docker, Docker configuration is placed under host `/run`, and logout/removal occurs
after deployment. The token is never a Terraform variable and is therefore not stored in state.
