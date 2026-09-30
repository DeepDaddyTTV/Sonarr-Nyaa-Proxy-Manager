---
layout: default
title: Connect Sonarr and Prowlarr
description: Give the proxy permission to search your sources and add its entries to Sonarr.
permalink: /connections/
---

An **API key** lets one app communicate with another without using your browser login. The proxy needs Prowlarr's key to find and search your indexers, and Sonarr's key to identify series and add the proxy's search entries. Use the key from each app in its matching field; they are not interchangeable.

## 1. Find the API Keys

In **Prowlarr / Settings / General**, find **Security / API Key**. Copy it privately into the proxy's Prowlarr key field. In **Sonarr / Settings / General**, repeat for Sonarr. Your manager password is not an API key.

<figure><a href="{{ '/assets/screenshots/prowlarr-general.jpg' | relative_url }}"><img src="{{ '/assets/screenshots/prowlarr-general.jpg' | relative_url }}" alt="Prowlarr General settings with a nonfunctional documentation API key" /></a><figcaption>Real Prowlarr interface with synthetic configuration. The placeholder key cannot authenticate.</figcaption></figure>

<figure><a href="{{ '/assets/screenshots/sonarr-general.jpg' | relative_url }}"><img src="{{ '/assets/screenshots/sonarr-general.jpg' | relative_url }}" alt="Sonarr General settings with a documentation-only API key" /></a><figcaption>Sonarr's separate key is used for metadata and explicit proxy-indexer registration, not downloads.</figcaption></figure>

## 2. Save Proxy Settings

<figure><a href="{{ '/assets/screenshots/proxy-settings.jpg' | relative_url }}"><img src="{{ '/assets/screenshots/proxy-settings.jpg' | relative_url }}" alt="Full proxy Settings tab including Anime and TV routing labels" /></a><figcaption>Saved-key placeholders do not reveal stored values. Example service names need a shared network.</figcaption></figure>

1. Enter the Prowlarr and Sonarr **base URLs** and their separate API keys. A base URL is the app's address, such as `http://sonarr:8989`, without a page path like `/settings/general`. Use the addresses from the [installation guide]({{ '/installation/#networking' | relative_url }}) that match your setup.
2. Enter the **Proxy base URL** reachable from Sonarr. Omit `/manager/` and `/api`.
3. Leave **Feed API key** blank to keep the persistent generated key. For manual Torznab setup, set a known unique key privately instead.
4. For Standard-numbered anime, enter existing tag labels under **Series routing**; otherwise leave them blank for Series Type routing.
5. **Save settings**, then test each saved connection. Tests do not use unsaved inputs.

Blank key inputs keep saved values. Keys are never returned to the browser. Nonempty environment values are read-only and take precedence.

## 3. Keep Your Existing Prowlarr Connection

<figure><a href="{{ '/assets/screenshots/prowlarr-sonarr-app.jpg' | relative_url }}"><img src="{{ '/assets/screenshots/prowlarr-sonarr-app.jpg' | relative_url }}" alt="Prowlarr Sonarr application editor with synthetic URLs and key" /></a><figcaption>The original application stays intact. Discovery reads sources; it does not write Prowlarr applications or indexers.</figcaption></figure>

Use **Prowlarr / Settings / Apps** for the normal connection. Its API key is Sonarr's key. The Prowlarr Server URL must be reachable from Sonarr; the Sonarr Server URL must be reachable from Prowlarr. Browser URLs may differ.

You do not need to remove this connection. Prowlarr continues managing the search entries it added to Sonarr; the proxy manages only its own entries. This means an original result can appear alongside a version changed by the proxy's rules. The original result is not filtered by those rules.

If Prowlarr uses **Full Sync**, it may overwrite manual edits to the Sonarr entries it manages. Make changes to those entries through Prowlarr instead. See [Prowlarr's official setup guide](https://wiki.servarr.com/prowlarr/quick-start-guide).

## Optional: Enter Connections in Compose

If you prefer setting connections in `.env` instead of the Settings page, the Compose example already supports these variables. This is optional; you do not need to use both methods.

```yaml
environment:
  PROWLARR_URL: ${PROWLARR_URL:-}
  PROWLARR_API_KEY: ${PROWLARR_API_KEY:-}
  SONARR_URL: ${SONARR_URL:-}
  SONARR_API_KEY: ${SONARR_API_KEY:-}
  PROXY_PUBLIC_URL: ${PROXY_PUBLIC_URL:-}
  PROXY_API_KEY: ${PROXY_API_KEY:-}
  SONARR_ANIME_TAG: ${SONARR_ANIME_TAG:-}
  SONARR_TV_TAG: ${SONARR_TV_TAG:-}
```

Keep actual values in your untracked `.env`. Next: [Create feeds]({{ '/feeds/' | relative_url }}).
