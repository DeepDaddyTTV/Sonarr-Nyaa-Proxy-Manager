---
layout: default
title: Troubleshooting
description: Isolate the failing connection, feed, and request before changing settings.
permalink: /troubleshooting/
---

## Connection Test Fails

Save Settings first. Check base URL, API key, and reachability **from the proxy container**, not just your browser. Shared-network peers use service names; native Docker Desktop host apps use `host.docker.internal`. Sonarr, Prowlarr, and proxy keys are separate. Test saved connections independently.

## Source Not Discovered

Test it in Prowlarr: it must be enabled, searchable, and torrent-based. Save the connection and discover again. Proxy entries are skipped to avoid recursion. Discovery alone does not add sources to feeds or the legacy endpoint.

## Standard Anime Uses the Wrong Feed

Check the show's existing anime tag, saved proxy routing label, and a fresh Sonarr sync. Anime needs `5070` in regular Categories for Standard numbering. TV must not use `5070` or broad parent `5000`. Unknown/ambiguous series fail closed; allow five minutes for cached metadata.

Check the **Indexer** column. A raw Prowlarr result is outside the proxy, not evidence that proxy routing failed. See [Routing]({{ '/routing/' | relative_url }}).

## Episodes and Packs Mix

Verify the result's indexer and feed profile. Episode/season isolation built-ins should be enabled. Episode requests have `season` and `ep`; season requests omit `ep`. Preferences do not override classification. Missing individual releases should return no proxy episode candidate, not a substituted pack.

## Empty / Disabled Feeds

Check selected sources, feed enable state, request categories, tags, and custom exclusions. Disable a feed and sync to disable its Sonarr entry. Rediscover after Prowlarr source changes. Environment-declared feeds remain read-only until `PROXY_FEEDS_JSON` is removed and the container recreated.

## Manual Torznab Test Fails

Separate base URL and API Path. Use `/feeds/<id>/api` for new feeds, `/api` for legacy, never `/manager/`. New feeds need the proxy key. Generated keys are sent during sync; set a known key privately for manual setup. See the [setup table]({{ '/feeds/#manual-torznab-configuration' | relative_url }}).

## Manager 404 or Login Problems

Open `/manager/` on the actual proxy port. `/health` alone does not prove reverse-proxy backend/path correctness. Configure both auth variables. Secure cookies require HTTPS. DNS, VPN routes, ingress, and application health are separate layers.

## Safe Bug Reports

Include build number, source type, anonymized title, request shape, rule names, expected and actual outcome. Do not post API keys, cookies, private hostnames, environment dumps, `integrations.json`, or media paths. Review exports and images before attaching them publicly.
