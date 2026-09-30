---
layout: default
title: Connect the Arr Apps
description: API connections in Settings or Compose, without replacing your Prowlarr link.
permalink: /connections/
---

## 1. Find the API Keys

In **Prowlarr / Settings / General**, find **Security / API Key**. Copy it privately into the proxy's Prowlarr key field. In **Sonarr / Settings / General**, repeat for Sonarr. Your manager password is not an API key.

<figure><a href="{{ '/assets/screenshots/prowlarr-general.jpg' | relative_url }}"><img src="{{ '/assets/screenshots/prowlarr-general.jpg' | relative_url }}" alt="Prowlarr General settings with a nonfunctional documentation API key" /></a><figcaption>Real Prowlarr interface with synthetic configuration. The placeholder key cannot authenticate.</figcaption></figure>

<figure><a href="{{ '/assets/screenshots/sonarr-general.jpg' | relative_url }}"><img src="{{ '/assets/screenshots/sonarr-general.jpg' | relative_url }}" alt="Sonarr General settings with a documentation-only API key" /></a><figcaption>Sonarr's separate key is used for metadata and explicit proxy-indexer registration, not downloads.</figcaption></figure>

## 2. Save Proxy Settings

<figure><a href="{{ '/assets/screenshots/proxy-settings.jpg' | relative_url }}"><img src="{{ '/assets/screenshots/proxy-settings.jpg' | relative_url }}" alt="Full proxy Settings tab including Anime and TV routing labels" /></a><figcaption>Saved-key placeholders do not reveal stored values. Example service names need a shared network.</figcaption></figure>

1. Enter the Prowlarr and Sonarr **base URLs** and their separate API keys.
2. Enter the **Proxy base URL** reachable from Sonarr. Omit `/manager/` and `/api`.
3. Leave **Feed API key** blank to keep the persistent generated key. For manual Torznab setup, set a known unique key privately instead.
4. For Standard-numbered anime, enter existing tag labels under **Series routing**; otherwise leave them blank for Series Type routing.
5. **Save settings**, then test each saved connection. Tests do not use unsaved inputs.

Blank key inputs keep saved values. Keys are never returned to the browser. Nonempty environment values are read-only and take precedence.

## 3. Preserve the Direct Prowlarr Link

<figure><a href="{{ '/assets/screenshots/prowlarr-sonarr-app.jpg' | relative_url }}"><img src="{{ '/assets/screenshots/prowlarr-sonarr-app.jpg' | relative_url }}" alt="Prowlarr Sonarr application editor with synthetic URLs and key" /></a><figcaption>The original application stays intact. Discovery reads sources; it does not write Prowlarr applications or indexers.</figcaption></figure>

Use **Prowlarr / Settings / Apps** for the normal connection. Its API key is Sonarr's key. The Prowlarr Server URL must be reachable from Sonarr; the Sonarr Server URL must be reachable from Prowlarr. Browser URLs may differ.

Full Sync can overwrite manual edits to Prowlarr-owned Sonarr indexers. The proxy only syncs its own mapped entries. Raw results are not filtered and can appear beside rewritten copies. See [Prowlarr's official setup guide](https://wiki.servarr.com/prowlarr/quick-start-guide).

## Compose Equivalent

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
