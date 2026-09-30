---
layout: default
title: Installation
description: A small container, persistent configuration, and private network access.
permalink: /installation/
---

## Requirements

- Docker Engine / Docker Desktop or another OCI runtime.
- Sonarr, a working torrent download client, and outbound access to your sources.
- Prowlarr for discovery, or individual Torznab endpoints from Prowlarr / Jackett. Direct Nyaa works without Prowlarr.
- Reachability from proxy to Arr apps and from Sonarr to the proxy.
- A persistent `/data` volume and manager login credentials.

No host Python installation, special DNS, Tailscale, reverse proxy, WAN port forward, or Nyaa account is required. Private ingress tools are optional infrastructure, not dependencies.

## Compose

Download [compose.yaml]({{ '/assets/examples/compose.yaml' | relative_url }}), [env.example]({{ '/assets/examples/env.example' | relative_url }}), and the optional [feed override]({{ '/assets/examples/compose.feeds.yaml' | relative_url }}). Put the first two beside each other, name the environment file `.env`, and set a unique administrator password.

```sh
docker network create sonarr-net
docker compose up -d
```

Attach **both Sonarr and Prowlarr** containers to `sonarr-net` in their own Compose configurations. The example only creates the proxy, not your Arr apps or download client. Open `http://127.0.0.1:8787/manager/`.

| Connection | Shared-network base URL |
| --- | --- |
| Prowlarr, as the proxy sees it | `http://prowlarr:9696` |
| Sonarr, as the proxy sees it | `http://sonarr:8989` |
| Proxy, as Sonarr sees it | `http://sonarr-proxy-manager:8787` |

Blank URL/key variables are editable in **Settings**. Nonempty environment values override saved values and are read-only. Recreate the container after environment changes.

## Networking

**Containers on one host:** keep the loopback-only `127.0.0.1:8787:8787` host map. Sonarr reaches the proxy through the shared network, not the host map.

**Native Arr apps on the Docker Desktop host:** use `http://host.docker.internal:8989` and `http://host.docker.internal:9696` from the proxy. Sonarr on the same host can use `http://127.0.0.1:8787` as the proxy base. `localhost` inside a container points back to that container.

**Docker Engine on Linux:** if your runtime lacks the host alias, add:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

**Arr apps on another machine:** publish `"${HOST_LAN_IP}:8787:8787"` instead and define your private interface address in `.env`. Allow only trusted LAN/VPN clients through the firewall. Do not forward port 8787 through your internet router. A private HTTPS reverse proxy can target this host port; use `AUTH_COOKIE_SECURE=true` only for HTTPS access.

`PROXY_PUBLIC_URL` means **Sonarr-reachable URL**, not public exposure. A public image does not require a public manager site.

## Image Tags and Updates

| Tag | Use |
| --- | --- |
| `latest` | Normal rolling main-branch installation |
| `dev` | Rolling testing installation |
| `build-42` | Pin workflow build number 42, if that successful build exists |

`latest` and `dev` currently move together after successful main builds, not separate stable/beta release tracks. Find the successful run number in the [publish workflow](https://github.com/DeepDaddyTTV/Sonarr-Proxy-Manager/actions/workflows/publish-dev.yml), not a commit SHA. Set `IMAGE_TAG=build-<number>` to pin it. Keep your testing Compose on `dev`.

```sh
docker compose pull sonarr-proxy-manager
docker compose up -d sonarr-proxy-manager
```

## Keep Configuration Private

Back up `/data` privately. `integrations.json` contains connections, keys, discovery snapshots, and owned-entry mappings. Feed rules live in `feed-rules/`; legacy rules in `custom-rules.json`. Manager exports contain only the selected rule profile. Never commit a populated `.env` or `/data`. Direct `*_FILE` secret loading is not implemented.

Next: [Connect the Arr apps]({{ '/connections/' | relative_url }}).
