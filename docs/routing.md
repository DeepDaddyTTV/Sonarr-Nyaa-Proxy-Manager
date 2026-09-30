---
layout: default
title: Anime and TV Routing
description: Choose which proxy search entries Sonarr uses for anime and TV series.
permalink: /routing/
---

A **tag** is a label you assign to a series in Sonarr. This setup uses labels such as `anime` and `tv` to choose the appropriate proxy feed; the names are examples, and you can use labels you already have. It does not change episode numbering or the series' type.

## Standard Numbering Works

You do not have to change anime to **Series Type = Anime**. Use existing `anime` and `tv` tags on the intended Sonarr series, then enter those **labels** under **Settings / Series routing** in the proxy. Save and sync feeds again. The manager never modifies series types, tags, or episode ordering.

<figure><a href="{{ '/assets/screenshots/proxy-settings.jpg' | relative_url }}"><img src="{{ '/assets/screenshots/proxy-settings.jpg' | relative_url }}" alt="Proxy Settings with anime and tv routing labels" /></a><figcaption>Existing labels resolve to Sonarr tag IDs. Nonempty environment values control the same fields.</figcaption></figure>

```yaml
environment:
  SONARR_ANIME_TAG: anime
  SONARR_TV_TAG: tv
```

| Series | Type | Tag | Proxy feed |
| --- | --- | --- | --- |
| Anime show | Standard | `anime` | Nyaa Anime |
| TV show | Standard / Daily | `tv` | Lime TV |
| Both tags | Standard | `anime`, `tv` | Anime wins; TV feed rejected |
| Untagged / unknown | Any | None | Rejected by tag-required feeds |

<figure><a href="{{ '/assets/screenshots/sonarr-torznab-tags.jpg' | relative_url }}"><img src="{{ '/assets/screenshots/sonarr-torznab-tags.jpg' | relative_url }}" alt="Sonarr Torznab indexer editor showing the anime series tag restriction" /></a><figcaption>Sonarr's Tags field restricts this indexer to series with the matching label. This full interface capture uses documentation-only data.</figcaption></figure>

The Anime feed gets `5070` in **regular Categories and Anime Categories**, allowing Standard requests to reach it. The TV feed uses specific TV subcategories and no Anime Categories. The proxy also checks the requested series before calling upstreams, resolving identifiers or an exact normalized main/alternate title. Unknown or ambiguous classifications fail closed.

With only an Anime tag configured, TV feeds accept known non-Anime-tagged shows. A configured TV tag must match. Category-only requests without series identity are allowed for Sonarr's save-time validation; RSS stays disabled. Metadata can be cached for five minutes.

## Series Type Routing

Leave both labels blank, save, and sync. Anime feeds use only **Anime Categories = 5070**; TV feeds use only regular TV subcategories. Sonarr's series type chooses the field, not the indexer name. Broad parent **TV = 5000** includes Anime, so virtual TV categories exclude it. An upstream exposing only parent TV can still be searched through `5000` without changing virtual routing.

## Raw Prowlarr Entries Are Separate

They remain unchanged and are not filtered by proxy rules. For Standard anime, `5070` in Prowlarr's Anime Sync Categories alone does **not** make Sonarr infer anime from a tag. Raw indexer categories/tags need deliberate configuration if you want strict separation there too. Prowlarr application/indexer tags are not automatically Sonarr series tags; Full Sync can overwrite manual edits to Prowlarr-owned fields.

The proxy provides isolated lanes without interrupting the direct link. Review raw entries separately if duplicate/cross-category raw results are unwanted. See [Prowlarr's application guide](https://wiki.servarr.com/prowlarr/quick-start-guide).
