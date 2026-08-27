# OCI Infrastructure

This root creates only OCI infrastructure: network, VM, Vault, Vault key, Dynamic Group, and the IAM
policy required for Instance Principal access. It does not deploy Agent Nebula containers.

Initialize it against the S3 backend created by `terraform/bootstrap`:

```bash
export TF_STATE_BUCKET=...
export TF_STATE_REGION=...
cp terraform/infrastructure/terraform.tfvars.example terraform/infrastructure/terraform.tfvars
make tf-infra-init
make tf-infra-plan
make tf-infra-apply
```

The VM bootstraps Docker, `uv`, OCI CLI, and the standard `/opt/agent-nebula` and
`/run/agent-nebula` roots. Persistent swap is disabled by default because plaintext runtime security
material is intentionally confined to `/run`.
