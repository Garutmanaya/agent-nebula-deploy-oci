# Agent Nebula LOCAL Setup

This guide installs Agent Nebula on an AMD64 development host using images published to GitHub
Container Registry (GHCR). Application repositories own their Dockerfiles; this repository owns
image build/push orchestration and the deployment lifecycle.

## 1. Runtime model

LOCAL uses the same persistent/runtime directory contract as OCI, but durable secrets remain
plaintext on the development host.

```text
/opt/agent-nebula/                    durable host state
├── deploy/                           generated deployment profile files
├── nebula/
│   ├── core/
│   │   ├── config/
│   │   ├── secrets/                  durable LOCAL secret source
│   │   ├── certs/
│   │   └── data/
│   └── console/
├── database/
│   ├── secrets/
│   ├── certs/
│   └── data/                         PostgreSQL durable data
├── explorer/
│   ├── secrets/
│   ├── certs/
│   └── data/                         Explorer durable sessions/state
├── oauth/
├── policy/
├── playground/
│   ├── container/
│   ├── backend/
│   └── ui/
├── nebula-ca/
└── cloudflare/                       Cloudflare host configuration when enabled

/run/agent-nebula/                    ephemeral runtime state
├── nebula/core/
├── nebula/console/
├── database/
├── explorer/
├── oauth/
├── policy/
├── playground/
└── nebula-ca/
```

Applications read private material from `/run/agent-nebula`, never directly from durable `/opt`
paths. In LOCAL mode the container entrypoint copies durable files into its runtime tree without
encryption/decryption.

Application data remains under `/opt` and is never moved to `/run`.

## 2. Prerequisites

The host requires:

- Linux AMD64;
- Docker Engine and Docker Compose plugin;
- Docker Buildx when building images;
- Python 3.12;
- `make`;
- sibling Agent Nebula repositories when building images;
- `cloudflared` only when the Cloudflare profile is used.

The repository layout used by image builds is:

```text
workspace/
├── agent-nebula-deploy-oci/
├── agent-nebula-utils/
├── agent-nebula-core/
├── agent-nebula-oauth/
├── agent-nebula-policy/
├── agent-nebula-policy-sdk/
├── agent-nebula-explorer/
├── agent-nebula-playground/
├── agent-nebula-sdk/
├── agent-nebula-runtime/
├── agent-nebula-connect/
└── agent-nebula-plugins/
```

For Ubuntu/Debian hosts using Cloudflare, install `cloudflared` from the signed Cloudflare package
repository:

```bash
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | \
  sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' | \
  sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update
sudo apt-get install -y cloudflared
```

## 3. Configure GHCR

Edit `config/registry.json` once. The canonical image namespace is:

```text
ghcr.io/<owner>/agent-nebula/<image>:<tag>-<architecture>
```

For private packages, authenticate Docker with a token containing `read:packages` for installation
and `write:packages` when publishing:

```bash
export GHCR_USER='<github-user-or-org>'
export GHCR_TOKEN='<token>'
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
```

Do not put the token in repository files.

## 4. Build and publish images

Create/verify the multi-platform builder:

```bash
make builder
make check IMAGE=all
```

Build AMD64 images locally for inspection:

```bash
make amd-build IMAGE=all RELEASE=0.5.0
```

Publish AMD64 images to GHCR:

```bash
make amd-push IMAGE=all RELEASE=0.5.0
```

The publication produces both versioned and moving architecture tags, for example:

```text
0.5.0-amd64
latest-amd64
```

Installation never consumes local Docker image names. It always resolves images from GHCR.

## 5. Initialize LOCAL deployment

The installation selector is `TAG`; its default is `latest`. The lifecycle automatically appends
`-amd64`, so `TAG=latest` resolves `latest-amd64` and `TAG=0.5.0` resolves `0.5.0-amd64`.

Initialize the platform components:

```bash
make init TARGET=local PROFILE=local PRODUCT=policy TAG=latest
make init TARGET=local PROFILE=local PRODUCT=nebula TAG=latest
make init TARGET=local PROFILE=local PRODUCT=oauth TAG=latest
```

`TAG=latest` can be omitted because it is the default.

Force scopes retain the existing deployment semantics:

```bash
make init TARGET=local PROFILE=local PRODUCT=nebula FORCE=config
make init TARGET=local PROFILE=local PRODUCT=nebula FORCE=pki
make init TARGET=local PROFILE=local PRODUCT=nebula FORCE=database
make init TARGET=local PROFILE=local PRODUCT=nebula FORCE=all
```

## 6. Deploy the platform

Deploy the platform using the existing dependency order:

```bash
make deploy TARGET=local PROFILE=local PRODUCT=nebula TAG=latest
make health TARGET=local PROFILE=local PRODUCT=nebula TAG=latest
```

The Nebula lifecycle coordinates Policy, PostgreSQL/migrations, Core, OAuth and Console according to
the existing prerequisite checks.

Run the existing platform bootstrap:

```bash
make bootstrap TARGET=local PROFILE=local
```

Platform bootstrap remains interactive and intentionally does not create Provider API keys.

## 7. Create and import Provider API keys

Sign in to Console and create Provider API keys for Explorer and Playground. Each raw API key is
shown only at creation time.

Import Explorer:

```bash
make secret-import TARGET=local COMPONENT=explorer
```

Import Playground:

```bash
make secret-import TARGET=local COMPONENT=playground
```

The CLI prompts without terminal echo. LOCAL stores the keys in the existing durable plaintext
component secret paths; container startup copies them into `/run`.

## 8. Deploy Explorer and Playground

```bash
make init TARGET=local PROFILE=local PRODUCT=nebula COMPONENT=explorer TAG=latest
make deploy TARGET=local PROFILE=local PRODUCT=nebula COMPONENT=explorer TAG=latest
make health TARGET=local PROFILE=local PRODUCT=nebula COMPONENT=explorer TAG=latest

make init TARGET=local PROFILE=local PRODUCT=playground TAG=latest
make deploy TARGET=local PROFILE=local PRODUCT=playground TAG=latest
make health TARGET=local PROFILE=local PRODUCT=playground TAG=latest
```

## 9. Optional Cloudflare Tunnel

Cloudflare is an independent host-infrastructure step, but applications exposed through it must use
the `cloudflare` profile so public URLs and certificate SANs are generated correctly. Prepare the
Cloudflare profile before starting the public deployment:

```bash
make init TARGET=local PROFILE=cloudflare PRODUCT=policy
make init TARGET=local PROFILE=cloudflare PRODUCT=nebula
make init TARGET=local PROFILE=cloudflare PRODUCT=oauth
```

Create/authenticate the named tunnel with `cloudflared`. The default tunnel name is `agent-nebula`;
it can be overridden with `ANU_DEPLOY_CLOUDFLARE_TUNNEL_NAME`.

```bash
cloudflared tunnel login
cloudflared tunnel create agent-nebula
```

Route the required Console/API/Explorer hostnames to the tunnel, then initialize host integration:

```bash
make cloudflare-init TARGET=local PROFILE=cloudflare
make cloudflare-start TARGET=local PROFILE=cloudflare
make cloudflare-status TARGET=local PROFILE=cloudflare
```

Deploy the public profile only after the tunnel is configured:

```bash
make deploy TARGET=local PROFILE=cloudflare PRODUCT=nebula TAG=latest
make health TARGET=local PROFILE=cloudflare PRODUCT=nebula TAG=latest
make bootstrap TARGET=local PROFILE=cloudflare
```

The adapter reuses the existing Agent Nebula Cloudflare implementation. It creates:

```text
/opt/agent-nebula/cloudflare/config.yml
/opt/agent-nebula/cloudflare/credentials.json
/etc/systemd/system/cloudflared.service
```

Application origins remain HTTPS and Cloudflare validates them against the Agent Nebula root CA.

## 10. Upgrade images

Publish a new release, then install only the desired tag:

```bash
make amd-push IMAGE=all RELEASE=0.5.1
make redeploy TARGET=local PROFILE=local PRODUCT=nebula TAG=0.5.1
```

Repeat for Explorer/Playground if they are deployed separately. No image repository/registry input is
required during installation; `config/registry.json` owns the GHCR destination.

## 11. Stop and uninstall LOCAL

Stop without deleting durable state:

```bash
make stop TARGET=local PROFILE=local PRODUCT=playground
make stop TARGET=local PROFILE=local PRODUCT=nebula
make stop TARGET=local PROFILE=local PRODUCT=oauth
make stop TARGET=local PROFILE=local PRODUCT=policy
```

Remove Cloudflare host integration when configured:

```bash
make cloudflare-destroy TARGET=local PROFILE=cloudflare
```

Destroy deployment-owned containers and product state using the existing lifecycle:

```bash
make destroy TARGET=local PROFILE=local PRODUCT=playground
make destroy TARGET=local PROFILE=local PRODUCT=oauth
make destroy TARGET=local PROFILE=local PRODUCT=policy
make destroy TARGET=local PROFILE=local PRODUCT=nebula
```

After verifying that no required data remains, remove residual runtime state:

```bash
sudo rm -rf /run/agent-nebula
```

Only remove `/opt/agent-nebula` manually when a complete loss of PostgreSQL, Explorer and Playground
data is intended.

### Buildx ARM64 support

`make builder` uses the dedicated `agent-nebula-builder`. On an AMD64 development host it
installs the ARM64 `binfmt`/QEMU registration automatically when required and recreates only that
dedicated Buildx builder so BuildKit detects the additional platform. This requires permission to
run a privileged Docker helper container.

`make check IMAGE=all` is a metadata/build-context validation command and does not require the
`agent-nebula-utils` Python package to be installed in the deployment repository environment.
