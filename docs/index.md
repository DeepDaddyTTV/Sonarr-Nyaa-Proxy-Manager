---
layout: default
title: Getting Started
description: Filter Sonarr search results while keeping your existing Prowlarr setup.
---

Sonarr Proxy Manager helps Sonarr receive the right search results. For example, an episode search can exclude full-season packs, and a season search can exclude individual episodes. You can also prefer a release group, remove unwanted titles, or tidy the titles Sonarr receives.

Connect the manager to Prowlarr, choose the sources you want to search, and create an entry for each group of sources in Sonarr. Nyaa can have anime rules while LimeTorrents has different TV rules. Your existing Prowlarr entries stay in place and continue working normally.

<figure><a href="{{ '/assets/screenshots/proxy-main.jpg' | relative_url }}"><img src="{{ '/assets/screenshots/proxy-main.jpg' | relative_url }}" alt="Full Sonarr Proxy Manager rule library" /></a><figcaption>The current rule library. Built-ins start locked; unlock their icons to edit. Documentation demo, not a live library.</figcaption></figure>

## Start Here

Choose your installation guide: [Windows]({{ '/installation/windows/' | relative_url }}), [macOS]({{ '/installation/macos/' | relative_url }}), or [Linux]({{ '/installation/linux/' | relative_url }}). Each separates native Arr apps from Dockerized ones.

<div class="chapter-grid">
  <a href="{{ '/installation/' | relative_url }}"><span>01 / INSTALL</span><strong>Install with Docker</strong><p>Download the example files and start the app.</p></a>
  <a href="{{ '/connections/' | relative_url }}"><span>02 / CONNECT</span><strong>Connect Sonarr and Prowlarr</strong><p>Find their API keys and enter them in Settings.</p></a>
  <a href="{{ '/feeds/' | relative_url }}"><span>03 / SEARCH</span><strong>Add search entries to Sonarr</strong><p>Choose which sources each entry should search.</p></a>
  <a href="{{ '/rules/' | relative_url }}"><span>04 / CUSTOMIZE</span><strong>Add your rules</strong><p>Prefer releases, exclude titles, or change title text.</p></a>
  <a href="{{ '/mcp/' | relative_url }}"><span>05 / AI TOOLS</span><strong>Connect Codex or Claude</strong><p>Use MCP to read or edit rules and saved settings.</p></a>
</div>

## How It Works

1. Sonarr requests an episode or a season through one of the proxy's search entries.
2. The proxy searches the sources selected for that entry.
3. It applies that entry's rules and returns the remaining results to Sonarr.
4. Sonarr decides which release meets your quality settings and sends downloads to your usual download client.

An **indexer** is a source of search results, such as Nyaa or LimeTorrents. A **feed** is the proxy's search entry that you add to Sonarr. A **rule profile** is the set of rules used by that feed. You can edit these rules in the manager; you do not need to write code or XML.

## What Changes, What Doesn't

| The proxy does | The proxy does not |
| --- | --- |
| Filter exact-series episode and season searches | Download, import, or replace media files |
| Normalize accepted Anime pack titles | Change Sonarr series types or episode ordering |
| Annotate Dual Audio in Anime profiles | Guess every tracker's audio languages |
| Register its own feeds with explicit sync | Overwrite existing Prowlarr-owned indexers |
| Apply rules to selected sources in one profile | Filter your raw Prowlarr results |

Use the proxy for episode and season searches. It is not designed to collect weekly releases automatically through RSS (Sonarr's periodic check for newly posted releases). A season pack is not substituted for a missing individual episode.

Keep anime **Standard-numbered**? Use [tag routing]({{ '/routing/' | relative_url }}). Want a non-Nyaa tracker? Follow [discovery]({{ '/feeds/' | relative_url }}) and the [LimeTorrents walkthrough]({{ '/rules/#walkthrough-a-limetorrents-tv-rule' | relative_url }}). See [XML and configuration]({{ '/reference/' | relative_url }}) for response examples.

All screenshots use real interfaces with synthetic documentation data. No private hosts, real keys, paths, or library information are included. Click a screenshot for the full-resolution image.
