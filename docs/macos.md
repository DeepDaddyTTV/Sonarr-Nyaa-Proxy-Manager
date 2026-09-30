---
layout: default
title: macOS Setup
description: Run the proxy with native Mac apps or with apps in Docker Desktop.
permalink: /installation/macos/
---

Use **Option A** if Sonarr/Prowlarr are installed directly on your Mac, or **Option B** if they are Docker containers. You do not need to move existing apps into Docker. These files install only the proxy, not Sonarr, Prowlarr, Radarr, or your download client. Radarr can keep running alongside them, but this proxy supports Sonarr TV/anime searches, not Radarr movie searches.

## Install Docker Desktop

Install [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/) for your Mac's processor and supported macOS version. Start it and wait until the engine is running. Open **Terminal**:

```sh
mkdir -p "$HOME/sonarr-proxy-manager"
cd "$HOME/sonarr-proxy-manager"
docker version
docker compose version
```

## Option A: Native Mac Arr Apps

Download [compose.desktop-native.yaml]({{ '/assets/examples/compose.desktop-native.yaml' | relative_url }}) into that folder and rename it to `compose.yaml`. Download [env.example]({{ '/assets/examples/env.example' | relative_url }}) and rename it to `.env`. If using TextEdit, choose **Format / Make Plain Text**; do not save a rich-text document or add `.txt` to these filenames. Finder may hide `.env`; press **Command + Shift + .** to show hidden files.

In `.env`, set `AUTH_USERNAME` and `AUTH_PASSWORD`. Leave connection fields blank for **Settings**. The native-apps Compose publishes `127.0.0.1:8787:8787`, keeps settings in a Docker volume, and does not need a shared network.

```sh
docker compose up -d
docker compose ps
```

Open [the local manager](http://127.0.0.1:8787/manager/), sign in, and enter:

| Field | Native apps on this Mac |
| --- | --- |
| Sonarr base URL | `http://host.docker.internal:8989` |
| Prowlarr base URL | `http://host.docker.internal:9696` |
| Proxy base URL, as Sonarr sees it | `http://127.0.0.1:8787` |

Use each app's actual port and URL base if you changed them. [Docker Desktop provides `host.docker.internal`](https://docs.docker.com/desktop/features/networking/networking-how-tos/) so a container can connect to an app on the Mac. `localhost` inside the proxy would refer to the proxy container instead.

If a saved connection test fails, check the native app's bind address and any macOS firewall/security software blocking Docker Desktop. Keep access limited to trusted local connections; do not turn off your firewall or forward these ports to the internet.

## Option B: Docker Desktop Arr Apps

Download [compose.yaml for Docker apps]({{ '/assets/examples/compose.yaml' | relative_url }}) and [env.example]({{ '/assets/examples/env.example' | relative_url }}) into the proxy folder. Rename `env.example` to `.env` and set your manager login. This Compose uses a shared Docker network rather than the native-apps configuration.

Create `sonarr-net` once; skip if `docker network ls` already lists it:

```sh
docker network create sonarr-net
```

[Attach your existing Sonarr and Prowlarr containers]({{ '/installation/#attach-existing-docker-apps' | relative_url }}) to it. Keep their current volumes, images, ports, and other networks. Apply those changes from their own Compose folders before starting the proxy from its folder:

```sh
docker compose up -d
```

Open [the local manager](http://127.0.0.1:8787/manager/) and use:

| Field | Apps sharing `sonarr-net` |
| --- | --- |
| Sonarr base URL | `http://sonarr:8989` |
| Prowlarr base URL | `http://prowlarr:9696` |
| Proxy base URL, as Sonarr sees it | `http://sonarr-proxy-manager:8787` |

Replace the Arr service names if yours differ. A browser on the Mac uses the published loopback port; containers use their Docker service names.

## Mixed or Remote Setups

For one native app and one Dockerized app, use the Docker-apps Compose. Attach the Dockerized app to `sonarr-net`; use its service name for that app and `host.docker.internal` for the native app. Set the **Proxy base URL** to loopback for native Sonarr on the Mac, or the Docker service name for Sonarr on the shared network.

For another computer or a home server, use reachable LAN/private-VPN addresses. See [Home Network Access]({{ '/installation/#home-network-access' | relative_url }}). Continue with [Connections]({{ '/connections/' | relative_url }}) once the manager opens.
