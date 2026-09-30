---
layout: default
title: Installation
description: What you need, how to start the app, and where your settings are saved.
permalink: /installation/
---

## Before You Start

- Install Docker Desktop on Windows or macOS, or Docker Engine on your Linux server. Docker runs the app in a container, so you do not need to install Python yourself.
- Have Sonarr and its download client working first. This app changes search results; it does not download or import files itself.
- For the setup shown in this guide, have Prowlarr working with the indexers you want to use. Direct Nyaa also works without Prowlarr; Jackett and other Torznab-compatible sources are additional options.
- Use addresses that let Sonarr, Prowlarr, and the proxy connect to each other. The examples below cover a shared Docker network and apps installed directly on a computer.

You do not need a domain name, Nyaa account, VPN, or an open port on your internet router. You can start by opening the manager on the same computer where Docker runs.

## Install with Docker Compose

Docker Compose starts a container from a configuration file. The example `compose.yaml` tells Docker which app to run, how to open it, and where to keep its settings. The `.env` file holds your login details and optional connection settings.

1. Create a folder for the app on the computer running Docker.
2. Download [compose.yaml]({{ '/assets/examples/compose.yaml' | relative_url }}) and [env.example]({{ '/assets/examples/env.example' | relative_url }}) into that folder.
3. Rename `env.example` to `.env`. Open it in a text editor and set `AUTH_USERNAME` and `AUTH_PASSWORD` to the login you want to use for the manager. Leave the Sonarr and Prowlarr connection fields blank for now; you can fill them in through the app.
4. Create the Docker network below; the supplied Compose file needs it even when Sonarr and Prowlarr are installed outside Docker. If those apps also run in Docker, attach them to this network as described next. Otherwise, use the corresponding [networking example](#networking) for their addresses.

Open a terminal in the folder you created and run this once. If a network named `sonarr-net` already exists, you can reuse it and skip this command:

```sh
docker network create sonarr-net
```

**Only if Sonarr and Prowlarr also run in Docker:** add `sonarr-net` to their existing Compose files so all three apps can communicate. Keep their existing images, ports, volumes, and networks. This is an example of the **network additions**, not a replacement for their complete files:

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

Here, `default` represents their original network; keep any other networks your installation already uses. Apply the changes to each Arr app with `docker compose up -d` in its own folder. This may briefly restart those containers.

Then run the following in the **proxy's folder**:

```sh
docker compose up -d
```

Open `http://127.0.0.1:8787/manager/` in a browser on that same computer and sign in with the username and password from `.env`. The example starts only the proxy; it does not install Sonarr, Prowlarr, or a download client.

When you reach the proxy's Settings page, these addresses work if the containers share `sonarr-net` and use the service names shown:

| Connection | Shared-network base URL |
| --- | --- |
| Prowlarr, as the proxy sees it | `http://prowlarr:9696` |
| Sonarr, as the proxy sees it | `http://sonarr:8989` |
| Proxy, as Sonarr sees it | `http://sonarr-proxy-manager:8787` |

Connection fields left blank in `.env` can be changed in **Settings**. If you put a connection value in `.env`, that value takes priority and its field becomes read-only in the app. After editing `.env`, run `docker compose up -d` again to apply the change.

## Networking

**All three apps run in Docker on one computer:** the shared network lets the containers communicate using their service names. Keep `127.0.0.1:8787:8787` in the proxy's Compose file; this makes the browser manager accessible only from that computer. Sonarr reaches it through the Docker network instead.

**Sonarr and Prowlarr are installed directly on the computer running Docker Desktop:** enter `http://host.docker.internal:8989` for Sonarr and `http://host.docker.internal:9696` for Prowlarr in the proxy's Settings. Sonarr on that computer can reach the proxy at `http://127.0.0.1:8787`. Do not use `localhost` for the Arr addresses inside the proxy: inside a container, that name refers to the container itself, not your computer.

**Linux, with Sonarr or Prowlarr installed outside Docker:** if `host.docker.internal` does not resolve, add this under the proxy service in `compose.yaml`:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

**You need access from another computer:** replace the `127.0.0.1:8787:8787` port entry with `"${HOST_LAN_IP}:8787:8787"`. Add `HOST_LAN_IP=your-server-address` to `.env`, replacing `your-server-address` with that computer's address on your home network. Sonarr and your browser can then use `http://your-server-address:8787`. Configure the computer's firewall to allow only trusted devices on your home network or VPN, and do not forward port 8787 on your internet router.

The **Proxy base URL** must be an address Sonarr can reach. Its environment variable is named `PROXY_PUBLIC_URL`, but that does not mean you need to put the app on the internet. If you already use a private HTTPS reverse proxy, you can use its address and set `AUTH_COOKIE_SECURE=true`; leave that setting `false` for the HTTP examples above.

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

## Saving and Backing Up Your Settings

The app stores its settings in a folder called `/data` inside the container. The supplied Compose file keeps this folder in a Docker volume, so your settings remain when you update the container. Keep the same volume when updating; deleting it deletes the saved settings.

Use **Export configuration** in the manager to download the rules for the selected profile. This is useful for saving or sharing rules, but it does not include your API keys, connections, or other profiles. To make a complete backup, also back up the Docker data volume and your `.env` file using your usual Docker backup method.

These backups include API keys, which let the app access Sonarr and Prowlarr. Treat them like passwords: keep the backup somewhere only you can access, and do not upload it to a public GitHub repository or include it in a support post. When sharing a problem, remove keys and passwords from screenshots or configuration examples.

For advanced startup configuration, the optional [feed override]({{ '/assets/examples/compose.feeds.yaml' | relative_url }}) defines feeds in Compose instead of the app. You can skip this for the normal setup.

Next: [Connect Sonarr and Prowlarr]({{ '/connections/' | relative_url }}).
