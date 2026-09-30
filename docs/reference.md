---
layout: default
title: XML and Configuration
description: Torznab requests, XML examples, environment variables, and API endpoints.
permalink: /reference/
---

## Per-Feed Requests

```text
GET /feeds/nyaa-anime/api?t=caps&apikey=YOUR_PROXY_API_KEY
GET /feeds/nyaa-anime/api?t=tvsearch&q=Moonrise&season=1&ep=6&cat=5070&apikey=YOUR_PROXY_API_KEY
GET /feeds/nyaa-anime/api?t=tvsearch&q=Moonrise&season=1&cat=5070&apikey=YOUR_PROXY_API_KEY
GET /feeds/lime-tv/api?t=tvsearch&q=Example%20Show&season=1&ep=2&cat=5040&apikey=YOUR_PROXY_API_KEY
```

Omit `ep` for season searches. New feeds require a key; `X-Api-Key` is also accepted. Sonarr can supply TVDB/IMDb identifiers. Tag routing requires a resolvable series that meets the policy.

## Legacy Requests and XML

The examples below describe legacy `/api` and abbreviated Anime output. Anime virtual feeds use the same item transformations. IDs, dates, hashes and sizes are illustrative; TV profiles do not add Japanese/English by default.

{% capture project_readme %}{% include_relative README.md %}{% endcapture %}
{{ project_readme | split: "## Torznab Requests and XML Examples" | last | split: "## AI / MCP Integration" | first }}

Manager configuration responses include an `ETag` revision. A client can send that value as `If-Match` on a PUT to rules, feeds, or settings; a stale revision returns HTTP `409` without saving. The [MCP client]({{ '/mcp/' | relative_url }}) requires revisions for rule/feed edits. Existing browser clients remain compatible without this optional header.

## Build and Test

```sh
python -m pip install -r requirements-mcp.txt
python -m unittest discover -q
node --check app.js
node --check auth.js
node --check site-icon.js
docker build -t sonarr-proxy-manager:dev .
```

Use Python 3.10 or newer for the MCP tests. They run against temporary local settings and mocked Arr actions, not your real Sonarr library.

Download [Compose]({{ '/assets/examples/compose.yaml' | relative_url }}) or return to [Installation]({{ '/installation/' | relative_url }}).
