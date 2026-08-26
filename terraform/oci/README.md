# OCI Terraform deployment

This Terraform root recreates the manually validated Agent Nebula OCI host and its minimal network.
It intentionally provisions infrastructure only; Agent Nebula application containers remain owned by
the deployment/image pipeline in this repository.

## Resources

- VCN `10.0.0.0/16` with OCI DNS enabled
- public subnet `10.0.0.0/24`
- Internet Gateway and `0.0.0.0/0` route
- security list with SSH-only ingress and unrestricted egress
- `VM.Standard.A1.Flex`, default 2 OCPU / 12 GiB
- compatible Canonical Ubuntu 22.04 image discovered dynamically for the selected shape
- ephemeral public IPv4 for bootstrap
- cloud-init bootstrap for swap, Docker Engine, Buildx/Compose, and Agent Nebula runtime directories

No Agent Nebula application ports or PostgreSQL port are opened publicly. Application ingress is
expected to use Cloudflare Tunnel after host bootstrap.

## OCI CLI/provider credentials

Use the normal OCI SDK configuration in `~/.oci/config`. Do not store API private keys or credentials
inside Terraform files.

Create a local variables file:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `region`, `compartment_ocid`, and `ssh_public_key_path`.

## Lifecycle

```bash
terraform init
terraform fmt -check
terraform validate
terraform plan
terraform apply
```

After creation:

```bash
terraform output -raw instance_public_ip
terraform output ssh_command
```

Destroy the entire prototype environment with:

```bash
terraform destroy
```

## Shielded Instance

The current Terraform root deliberately does not force `platform_config` shielded-boot flags yet.
OCI only accepts platform configuration values supported by the selected shape, and the provider
returns an error for unsupported combinations. During the manual A1 validation, record the exact
shielded configuration reported by OCI. Once confirmed for `VM.Standard.A1.Flex`, add those flags to
`oci_core_instance.agent_nebula` rather than silently falling back to a different shape.

## Security note

`ssh_source_cidr = "0.0.0.0/0"` is provided only because residential public IPs can change. SSH
must remain key-only. Once Cloudflare administrative access is established, remove public SSH or
restrict this CIDR and re-apply Terraform.
