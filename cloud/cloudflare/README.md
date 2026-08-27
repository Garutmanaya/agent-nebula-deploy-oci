# Agent Nebula Cloudflare adapter

Cloudflare Tunnel is optional host infrastructure. Agent Nebula remains Cloudflare-independent and
uses the same Compose lifecycle on LOCAL and OCI hosts. This adapter is copied from the proven
`agent-nebula-deploy` implementation and is invoked independently from application deployment.

Prepare the `cloudflare` profile first, then configure the existing named tunnel:

```bash
make cloudflare-init TARGET=local PROFILE=cloudflare
make cloudflare-status TARGET=local PROFILE=cloudflare
```

Use `TARGET=oci` when executing from the OCI host. The adapter resolves the tunnel by ID or name,
copies its credential JSON, renders `/opt/agent-nebula/cloudflare/config.yml`, installs/enables
`cloudflared.service`, and preserves the account-side tunnel object on `cloudflare-destroy`.

Normal image upgrades do not require tunnel reconfiguration.
