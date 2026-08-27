# OCI Application Deployment

This Terraform root orchestrates the existing `agent-nebula-deploy-oci` lifecycle over SSH. It does
not reimplement application initialization, Compose ordering, bootstrap, or health logic.

`deployment_phase = "platform"` performs:

```text
init Policy/Core/OAuth
-> deploy Policy/Database/Core/OAuth/Console
-> health
-> existing interactive platform-bootstrap
```

The bootstrap intentionally remains interactive and unchanged. It asks for Admin, Explorer,
Playground, and Studio account passwords inside the running Core container.

After bootstrap, create Explorer and Playground Provider API keys in Console and import them on the
VM using the existing secure CLI. Then set `deployment_phase = "applications"` and re-apply. That
phase initializes/deploys Explorer and Playground and runs their health checks.

Private GHCR packages require `GHCR_TOKEN` in the operator shell when Terraform applies. The token is
piped over SSH to Docker, Docker configuration is placed under host `/run`, and logout/removal occurs
after deployment. The token is never a Terraform variable and is therefore not stored in state.
