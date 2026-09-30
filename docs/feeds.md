---
layout: default
title: Feeds and Sonarr Setup
description: Choose your search sources and add separate proxy entries to Sonarr.
permalink: /feeds/
---

A **feed** is an entry Sonarr searches through the proxy. You choose which indexers it searches and which rules it applies. For example, `Sonarr Proxy Nyaa` can search Nyaa for anime while `Sonarr Proxy Lime` searches LimeTorrents for TV. They appear as separate entries in Sonarr, alongside any entries Prowlarr already added.

## Discover Sources

Add and test each tracker in Prowlarr first. After saving proxy Settings, choose **Proxy feeds / Discover Prowlarr indexers**. Discovery imports enabled searchable torrent indexers and skips proxy entries to prevent loops. It does not change Prowlarr.

<figure><a href="{{ '/assets/screenshots/prowlarr-indexers.jpg' | relative_url }}"><img src="{{ '/assets/screenshots/prowlarr-indexers.jpg' | relative_url }}" alt="Full Prowlarr indexer list with demo Nyaa and LimeTorrents sources" /></a><figcaption>Real Prowlarr interface with synthetic data. Tracker categories describe capabilities; your proxy feed chooses its search lane.</figcaption></figure>

## Separate Nyaa and LimeTorrents

1. **Add feed**: name `Sonarr Proxy Nyaa`, ID `nyaa-anime`, **Anime only**, discovered **Nyaa.si** source.
2. Add `Sonarr Proxy Lime`, ID `lime-tv`, **TV only (Standard / Daily)**, discovered **LimeTorrents** source.
3. Save each feed. Its ID forms `/feeds/<id>/api` and cannot be changed later.
4. Select **Edit rules** for the intended feed. Profiles are independent of each other and legacy `/api`.
5. Select **Sync feeds to Sonarr**. Startup never registers Sonarr entries automatically.

<figure><a href="{{ '/assets/screenshots/proxy-feeds-full.jpg' | relative_url }}"><img src="{{ '/assets/screenshots/proxy-feeds-full.jpg' | relative_url }}" alt="Full manager feed list with independent Anime and TV entries" /></a><figcaption>Several sources can share one feed/profile. Discovery does not automatically add sources to every feed.</figcaption></figure>

<figure><a href="{{ '/assets/screenshots/proxy-lime-feed.jpg' | relative_url }}"><img src="{{ '/assets/screenshots/proxy-lime-feed.jpg' | relative_url }}" alt="Complete Lime TV feed editor selecting only LimeTorrents" /></a><figcaption>Only LimeTorrents is selected here. Source-specific custom rules can narrow further in a multi-source feed.</figcaption></figure>

Repeated sync updates manager-owned entries without duplicates. Disable a feed and sync to disable its Sonarr entry; nothing is deleted. Feed name/category/enabled changes need another sync. Rule changes do not.

## Verify in Sonarr

<figure><a href="{{ '/assets/screenshots/sonarr-indexers.jpg' | relative_url }}"><img src="{{ '/assets/screenshots/sonarr-indexers.jpg' | relative_url }}" alt="Full Sonarr Indexers page retaining the original Prowlarr entry beside proxy entries" /></a><figcaption>The demo keeps the direct entry and adds Sonarr Proxy Nyaa and Sonarr Proxy Lime with anime / tv tags.</figcaption></figure>

Check names, categories, tags, and interactive search under **Sonarr / Settings / Indexers**. Run a separate interactive episode and season search. Packs should not appear as proxy episode candidates. No download is needed to test configuration.

## Manual Torznab Configuration

For manual setup choose **Settings / Indexers / Add / Torznab / Custom**. **Show Advanced** reveals API Path.

| Field | Nyaa Anime | Lime TV |
| --- | --- | --- |
| Name | `Sonarr Proxy Nyaa` | `Sonarr Proxy Lime` |
| URL | `http://sonarr-proxy-manager:8787` | Same reachable base URL |
| API Path | `/feeds/nyaa-anime/api` | `/feeds/lime-tv/api` |
| API Key | Your proxy key | Your proxy key |
| RSS | Disabled | Disabled |
| Interactive / Automatic | Enabled / optional | Enabled / optional |
| Categories, Series Type routing | Empty | Specific TV subcategories |
| Anime Categories | `5070` | Empty |
| Categories, Standard anime tag routing | `5070` | Specific TV subcategories |
| Tags, tag routing | Existing `anime` tag | Existing `tv` tag |

Do not append API Path to URL as well. New feeds always require a key. Generated keys are sent directly by **Sync feeds to Sonarr**; for manual setup set a known key privately in Settings or `PROXY_API_KEY`. Then **Test / Save**. The screenshot key is not usable.

<figure><a href="{{ '/assets/screenshots/sonarr-torznab.jpg' | relative_url }}"><img src="{{ '/assets/screenshots/sonarr-torznab.jpg' | relative_url }}" alt="Real Sonarr Torznab editor with synthetic URL and per-feed API Path" /></a><figcaption>Advanced settings can scroll independently of the page. See Routing for tag/category details.</figcaption></figure>

## Declarative and Legacy Feeds

Use the [Compose override]({{ '/assets/examples/compose.feeds.yaml' | relative_url }}) after replacing sample source IDs with your Prowlarr IDs. `PROXY_FEEDS_JSON` makes definitions read-only, not rules. Environment-declared feeds discover at startup unless disabled; they still require an explicit Sonarr sync.

Built-in Nyaa needs no Prowlarr. `UPSTREAM_INDEXERS_JSON` adds individual Prowlarr / Jackett Torznab endpoints, not arbitrary tracker URLs. See the [README's source examples](https://github.com/DeepDaddyTTV/Sonarr-Proxy-Manager#add-more-indexers).

Legacy `/api` retains its original sources/rules and does not adopt discovered sources. Keep RSS disabled. See [Sonarr's official indexer settings](https://wiki.servarr.com/sonarr/settings#indexers) and the [API reference]({{ '/reference/' | relative_url }}).
