---
layout: default
title: Installation
description: Choose your operating system and the way your Arr apps are installed.
permalink: /installation/
---

## Choose Your Setup

The proxy runs in Docker. Sonarr and Prowlarr can stay installed directly on your computer, or run in their own Docker containers. Choose the guide for the **computer that will run the proxy**, not the device you use to browse its UI.

| Computer | Native Sonarr/Prowlarr | Dockerized Sonarr/Prowlarr |
| --- | --- | --- |
| Windows / Docker Desktop | [Windows Option A]({{ '/installation/windows/#option-a-native-windows-arr-apps' | relative_url }}) | [Windows Option B]({{ '/installation/windows/#option-b-docker-desktop-arr-apps' | relative_url }}) |
| macOS / Docker Desktop | [macOS Option A]({{ '/installation/macos/#option-a-native-mac-arr-apps' | relative_url }}) | [macOS Option B]({{ '/installation/macos/#option-b-docker-desktop-arr-apps' | relative_url }}) |
| Linux / Docker Engine | [Linux Option B]({{ '/installation/linux/#option-b-native-linux-arr-services' | relative_url }}) | [Linux Option A]({{ '/installation/linux/#option-a-dockerized-arr-apps' | relative_url }}) |

Have Sonarr and its download client working first. The proxy changes search results; it does not download or import files itself. Prowlarr is used for the multi-indexer setup in this guide. Direct Nyaa also works without Prowlarr; Jackett and other Torznab sources are additional options.

Radarr can run alongside this setup, but this project does not integrate with Radarr or filter movie searches. Leave its existing configuration and Prowlarr connection unchanged.

You do not need a domain name, Nyaa account, VPN, host Python installation, or an open port on your internet router.

## Download the Right Files

Docker Compose starts the app from a configuration file. The `compose.yaml` file describes the container and network; `.env` stores your chosen login and optional connection settings. The OS guides explain how to save and use them.

| Example | When to use it |
| --- | --- |
| [Desktop native-apps Compose]({{ '/assets/examples/compose.desktop-native.yaml' | relative_url }}) | Windows/macOS Docker Desktop, with native Arr apps on the host |
| [Docker-apps Compose]({{ '/assets/examples/compose.yaml' | relative_url }}) | Arr containers on a shared Docker network, on any of the three OSes |
| [Linux native-apps Compose]({{ '/assets/examples/compose.linux-native.yaml' | relative_url }}) | Linux Engine, with native Arr services on the same host |
| [Environment template]({{ '/assets/examples/env.example' | relative_url }}) | All examples; rename to `.env` and set your manager login |

Save **one** Compose example as `compose.yaml`; these are alternatives, not files to combine. Keep connection values blank in `.env` if you want to edit them through **Settings**. Nonempty environment values take priority and their fields become read-only in the app. After changing `.env`, run `docker compose up -d` again.

The supplied files start only the proxy. They do not reinstall or replace your Arr apps. They use a named Docker volume for settings, so you do not need Windows drive paths or macOS/Linux folder permissions for `/data`.

## Attach Existing Docker Apps

This step is **only** for the Docker-apps example. Native-apps examples do not need `sonarr-net`.

Create the shared network once, unless it already exists:

```sh
docker network create sonarr-net
```

Add the network to your existing Sonarr and Prowlarr Compose files, keeping their current images, ports, volumes, and networks. This is a **network addition**, not a complete replacement stack:

```yaml
services:
  sonarr:
    networks:
      - default
      - sonarr-net
  prowlarr:
    networks:
      - default
      - sonarr-net

networks:
  sonarr-net:
    external: true
```

Here, `default` represents their original network; if yours has another name, retain that name instead. If the apps are in separate Compose projects, add the relevant service and network entries to each one. Apply each app's change from its own folder with `docker compose up -d`; this may briefly recreate those containers. Start the proxy from its own folder afterward.

If your container manager owns those Compose files, add the network through that manager instead. Do not create a second copy of your existing Arr containers.

## Home Network Access

The examples open the manager at `http://127.0.0.1:8787/manager/` only on the Docker computer. For a headless Linux server, the Linux guide includes an SSH tunnel.

If you want access from another trusted device, the change depends on the example:

- **Desktop native or shared-network Compose:** replace `"127.0.0.1:8787:8787"` with `"${HOST_LAN_IP}:8787:8787"`. Add `HOST_LAN_IP=your-server-address` to `.env`, replacing the placeholder with the Docker computer's home-network address.
- **Linux native host-network Compose:** change `HOST: 127.0.0.1` to the host's specific LAN/private-VPN address. There is no port map in host mode. Update the **Proxy base URL** in Settings to that reachable address.

Your browser and remote Sonarr can then use `http://your-server-address:8787`. Allow only trusted LAN/VPN clients through the host firewall; do not forward port 8787 on your internet router. A browser address is not necessarily the address containers should use: keep Docker service names for apps on the shared network.

The **Proxy base URL** is the address Sonarr uses to contact the proxy. Its variable is named `PROXY_PUBLIC_URL`, but it does not require internet exposure. If you already use a private HTTPS reverse proxy, use its reachable address and set `AUTH_COOKIE_SECURE=true`. Leave this setting `false` for the HTTP examples.

## Image Tags and Updates

| Tag | Use |
| --- | --- |
| `latest` | Normal rolling main-branch installation |
| `dev` | Rolling testing installation |
| `build-42` | Pin workflow build number 42, if that successful build exists |

`latest` and `dev` currently move together after successful main builds, not separate stable/beta release tracks. Find a successful run number in the [publish workflow](https://github.com/DeepDaddyTTV/Sonarr-Proxy-Manager/actions/workflows/publish-dev.yml), not a commit SHA. Set `IMAGE_TAG=build-<number>` to pin it. Keep your testing Compose on `dev`.

Run these commands from the proxy folder on any OS:

```sh
docker compose pull sonarr-proxy-manager
docker compose up -d sonarr-proxy-manager
```

## Saving and Backing Up Your Settings

The app stores settings in `/data` inside the container. Each example keeps this folder in a Docker volume, so settings remain when you update. Keep the same project folder and volume; deleting the volume, including with `docker compose down -v`, deletes saved settings.

**Export configuration** downloads rules for the selected profile, not API keys, connections, or other profiles. For a complete backup, also back up the Docker data volume and your `.env` file using your usual Docker backup method.

API keys let the app access Sonarr and Prowlarr. Treat backups like passwords: keep them somewhere only you can access, and remove keys/passwords from screenshots or configuration shared for support.

The optional [feed override]({{ '/assets/examples/compose.feeds.yaml' | relative_url }}) defines feeds in Compose rather than the UI. Skip it for normal setup.

Next: [Connect Sonarr and Prowlarr]({{ '/connections/' | relative_url }}).
