---
layout: default
title: Windows Setup
description: Choose a setup for native Windows apps or apps running in Docker Desktop.
permalink: /installation/windows/
---

Sonarr and Prowlarr do not have to run in Docker. If you installed them with Windows installers and open them through their tray icons or Windows services, use **Option A**. If they appear as containers in Docker Desktop, use **Option B**. Both examples start only the proxy; keep your existing Arr apps and download client.

**What about Radarr?** You can keep native or Dockerized Radarr running normally. This project filters TV/anime searches for **Sonarr**; it does not connect to Radarr, filter movie searches, or change Prowlarr's Radarr connection. There is no Radarr API-key field to fill in.

## Install Docker Desktop

Install [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/), following Docker's current Windows/WSL requirements. Use **Linux containers**, not Windows containers. Start Docker Desktop and wait until its engine is running.

Open **PowerShell**, create a folder, and enter it:

```powershell
New-Item -ItemType Directory -Force "$HOME\sonarr-proxy-manager"
Set-Location "$HOME\sonarr-proxy-manager"
docker version
docker compose version
```

## Option A: Native Windows Arr Apps

Download the [native-apps Compose file]({{ '/assets/examples/compose.desktop-native.yaml' | relative_url }}) into this folder and rename it to `compose.yaml`. Also download [env.example]({{ '/assets/examples/env.example' | relative_url }}) and rename it to `.env`. In File Explorer, enable **View / Show / File name extensions** so the files do not accidentally become `compose.yaml.txt` or `.env.txt`.

Open `.env` in a text editor. Set `AUTH_USERNAME` and `AUTH_PASSWORD` to your manager login. Leave connection fields blank so you can fill them in through **Settings** after starting the app.

This example uses Docker's normal network and publishes the manager only to this Windows computer. It does **not** require `sonarr-net`:

```yaml
{% include_relative assets/examples/compose.desktop-native.yaml %}
```

Run in PowerShell from the proxy folder:

```powershell
docker compose up -d
docker compose ps
```

Open [the local manager](http://127.0.0.1:8787/manager/) and sign in. In **Settings**, enter these base URLs, plus the API key from each corresponding app:

| Field | Native apps on this Windows computer |
| --- | --- |
| Sonarr base URL | `http://host.docker.internal:8989` |
| Prowlarr base URL | `http://host.docker.internal:9696` |
| Proxy base URL, as Sonarr sees it | `http://127.0.0.1:8787` |

`host.docker.internal` lets the proxy container reach Windows. `127.0.0.1` lets native Sonarr reach the proxy's published port. They are different addresses because one connection starts inside Docker and the other starts on Windows. See [Docker's host-networking explanation](https://docs.docker.com/desktop/features/networking/networking-how-tos/).

If Sonarr/Prowlarr uses a different port or a URL base such as `/sonarr`, use that actual port/path. If a connection test fails, check that the native app is running and its bind-address and Windows Firewall rules allow Docker Desktop to reach it. Do not disable the firewall or open the ports on your internet router.

## Option B: Docker Desktop Arr Apps

Download the [Docker-apps Compose file]({{ '/assets/examples/compose.yaml' | relative_url }}) as `compose.yaml` and [env.example]({{ '/assets/examples/env.example' | relative_url }}) as `.env`. Set your manager login in `.env`; leave connection fields blank for Settings.

This separate example connects the proxy to a shared Docker network:

```yaml
{% include_relative assets/examples/compose.yaml %}
```

Create the network once. If `docker network ls` already lists `sonarr-net`, skip creation:

```powershell
docker network create sonarr-net
```

Follow [Attach Existing Docker Apps]({{ '/installation/#attach-existing-docker-apps' | relative_url }}) to add Sonarr and Prowlarr to this network without replacing their existing configuration. Apply their network changes from each app's own Compose folder. Then start the proxy from **its** folder:

```powershell
docker compose up -d
```

Open [the local manager](http://127.0.0.1:8787/manager/) and use:

| Field | Apps sharing `sonarr-net` |
| --- | --- |
| Sonarr base URL | `http://sonarr:8989` |
| Prowlarr base URL | `http://prowlarr:9696` |
| Proxy base URL, as Sonarr sees it | `http://sonarr-proxy-manager:8787` |

Use the actual Sonarr/Prowlarr service names if yours differ. Docker containers must not use `127.0.0.1` to contact a different container: that address means themselves.

## Mixed or Remote Setups

If only one Arr app is native, use `host.docker.internal` for that app and its service name for the Dockerized app. Use the Docker-apps Compose and attach the Dockerized app to `sonarr-net`. The **Proxy base URL** depends on Sonarr: loopback for native Sonarr on this computer, or `sonarr-proxy-manager` for Dockerized Sonarr on the shared network.

For apps on another computer, use their home-network or private-VPN addresses instead. To open this manager from another device, follow [Home Network Access]({{ '/installation/#home-network-access' | relative_url }}).

Next: [Connect Sonarr and Prowlarr]({{ '/connections/' | relative_url }}).
