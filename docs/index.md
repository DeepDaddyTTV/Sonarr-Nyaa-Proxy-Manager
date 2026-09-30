---
layout: default
title: Your Searches, Your Rules
description: Keep the original Prowlarr connection. Add focused proxy feeds alongside it.
---

Sonarr Proxy Manager sits between Sonarr and selected Torznab indexers. Separate Anime and TV feeds get separate rule profiles, so a Nyaa transformation does not change a LimeTorrents result. Your original Prowlarr-managed entries continue working.

<figure><a href="{{ '/assets/screenshots/proxy-main.jpg' | relative_url }}"><img src="{{ '/assets/screenshots/proxy-main.jpg' | relative_url }}" alt="Full Sonarr Proxy Manager rule library" /></a><figcaption>The current rule library. Built-ins start locked; unlock their icons to edit. Documentation demo, not a live library.</figcaption></figure>

## Start Here

<div class="chapter-grid">
  <a href="{{ '/installation/' | relative_url }}"><span>01 / DEPLOY</span><strong>Install with Docker</strong><p>Compose, private access, storage, and image tags.</p></a>
  <a href="{{ '/connections/' | relative_url }}"><span>02 / CONNECT</span><strong>Link the Arr apps</strong><p>Find API keys and configure the Settings tab.</p></a>
  <a href="{{ '/feeds/' | relative_url }}"><span>03 / ROUTE</span><strong>Create virtual indexers</strong><p>Give Nyaa and Lime separate entries in Sonarr.</p></a>
  <a href="{{ '/rules/' | relative_url }}"><span>04 / REFINE</span><strong>Build your rules</strong><p>Scope preferences, exclusions, and rewrites.</p></a>
</div>

## What Changes, What Doesn't

| The proxy does | The proxy does not |
| --- | --- |
| Filter exact-series episode and season searches | Download, import, or replace media files |
| Normalize accepted Anime pack titles | Change Sonarr series types or episode ordering |
| Annotate Dual Audio in Anime profiles | Guess every tracker's audio languages |
| Register its own feeds with explicit sync | Overwrite existing Prowlarr-owned indexers |
| Apply rules to selected sources in one profile | Filter your raw Prowlarr results |

The default workflow is targeted episode/season searching, not a weekly RSS feed. A season pack is not substituted for a missing individual episode.

Keep anime **Standard-numbered**? Use [tag routing]({{ '/routing/' | relative_url }}). Want a non-Nyaa tracker? Follow [discovery]({{ '/feeds/' | relative_url }}) and the [LimeTorrents walkthrough]({{ '/rules/#walkthrough-a-limetorrents-tv-rule' | relative_url }}). See [XML and configuration]({{ '/reference/' | relative_url }}) for response examples.

All screenshots use real interfaces with synthetic documentation data. No private hosts, real keys, paths, or library information are included. Click a screenshot for the full-resolution image.
