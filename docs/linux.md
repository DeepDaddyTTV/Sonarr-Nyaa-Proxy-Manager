---
layout: default
title: Linux Setup
description: Docker Engine instructions, with separate routes for containerized and native Arr apps.
permalink: /installation/linux/
---

This page is for **Docker Engine running directly on Linux**, not Docker Desktop's virtual machine. Use **Option A** for containerized Sonarr/Prowlarr or **Option B** for native Linux services. Radarr can coexist unchanged; this project connects to Sonarr for TV/anime, not Radarr for movies.

## Install Docker Engine and Compose

Use [Docker's instructions for your Linux distribution](https://docs.docker.com/engine/install/) and install the [Compose plugin](https://docs.docker.com/compose/install/linux/). Check access from your terminal:

```sh
docker version
docker compose version
mkdir -p "$HOME/sonarr-proxy-manager"
cd "$HOME/sonarr-proxy-manager"
```

If your installation requires `sudo`, use it for the Docker commands below. Do not make the Docker socket world-writable; access to Docker is powerful administrative access. On a headless server, prepare files through your terminal or SSH file transfer rather than looking for a desktop app.

## Option A: Dockerized Arr Apps

Download [compose.yaml for Docker apps]({{ '/assets/examples/compose.yaml' | relative_url }}) and [env.example]({{ '/assets/examples/env.example' | relative_url }}) into the proxy folder. Rename the second file to `.env`. Set `AUTH_USERNAME` and `AUTH_PASSWORD`; leave connection fields blank to use **Settings**.

Create a shared network once, unless `docker network ls` already lists it:

```sh
docker network create sonarr-net
```

[Attach your existing Sonarr and Prowlarr containers]({{ '/installation/#attach-existing-docker-apps' | relative_url }}) to `sonarr-net` without replacing their volumes, ports, images, or original networks. Apply those changes from each app's own Compose folder. Start the proxy from its folder:

```sh
docker compose up -d
docker compose ps
```

| Field | Apps sharing `sonarr-net` |
| --- | --- |
| Sonarr base URL | `http://sonarr:8989` |
| Prowlarr base URL | `http://prowlarr:9696` |
| Proxy base URL, as Sonarr sees it | `http://sonarr-proxy-manager:8787` |

Use your actual service names if different. You do not need to publish extra Arr ports for these container-to-container connections.

## Option B: Native Linux Arr Services

Download the separate [Linux native-apps Compose]({{ '/assets/examples/compose.linux-native.yaml' | relative_url }}) and rename it to `compose.yaml`. Use the same [env.example]({{ '/assets/examples/env.example' | relative_url }}) renamed to `.env`, with your manager login filled in.

This example uses `network_mode: host` and sets `HOST: 127.0.0.1`. On Linux Engine, the proxy shares the host's network, so it can reach native Sonarr/Prowlarr even when they listen only on loopback. The manager also listens only on loopback; it is not exposed on every network interface. There is **no** `ports:` entry or shared Docker network in this example. [Docker explains host networking here](https://docs.docker.com/engine/network/drivers/host/).

```yaml
{% include_relative assets/examples/compose.linux-native.yaml %}
```

Run `docker compose up -d`, open the manager, and use:

| Field | Native services on the same Linux host |
| --- | --- |
| Sonarr base URL | `http://127.0.0.1:8989` |
| Prowlarr base URL | `http://127.0.0.1:9696` |
| Proxy base URL, as Sonarr sees it | `http://127.0.0.1:8787` |

Use the native apps' actual ports and URL bases. This host-network example is deliberately Linux-specific; do not use it as the Windows/macOS Docker Desktop guide.

## Open the Manager on a Headless Server

The examples listen only on the server's loopback address. `127.0.0.1` in your laptop's browser would mean the laptop, not the server. You can use an SSH tunnel without making a public port:

```sh
ssh -L 8787:127.0.0.1:8787 your-user@your-server
```

Replace the two placeholders with your SSH user and server. Leave that connection open, then open [the local manager](http://127.0.0.1:8787/manager/) on your laptop. This browser tunnel does not change the Docker/native base URLs entered in Settings.

For normal LAN/private-VPN access instead, see [Home Network Access]({{ '/installation/#home-network-access' | relative_url }}).

## Mixed Installations

**Native Sonarr, Dockerized Prowlarr:** use Option B, publish Prowlarr's port to host loopback, and enter `http://127.0.0.1:9696` (or its actual host port) for Prowlarr. Both Sonarr and the proxy use host loopback. Docker service names do not resolve through host networking.

**Dockerized Sonarr, native Prowlarr:** use Option A and put Sonarr on the shared network. Add the following under the proxy service so it can reach native Prowlarr:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

Use `http://host.docker.internal:9696` for native Prowlarr, but it must listen on an interface reachable from Docker, not only `127.0.0.1`. Limit access to the Docker network through the host firewall. Sonarr and the proxy still use Docker service names to reach each other. Do not use Option B's loopback-only manager with bridged Docker Sonarr: Sonarr's own loopback does not reach the host.

Next: [Connect Sonarr and Prowlarr]({{ '/connections/' | relative_url }}).
