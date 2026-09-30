---
layout: default
title: Rules That Fit Your Sources
description: Protected built-ins, scoped custom rules, and a non-Nyaa walkthrough.
permalink: /rules/
---

## Choose the Profile First

Open **Proxy feeds / Edit rules** or the **Rule profile** picker. A rule in `lime-tv` does not affect `nyaa-anime`, legacy `/api`, or raw Prowlarr entries.

## Built-In Rules

All eight start **locked**, not permanently immutable. Click the lock icon to unlock first, then edit/toggle. Lock again when finished. Unlocking changes available settings, not the built-in algorithm.

| Built-in | Behavior |
| --- | --- |
| Strip release years | Prevents bracketed years becoming episode numbers |
| Normalize season packs | Rewrites accepted Season / ordinal / Sxx forms to Sxx |
| Episode scans stay episodic | Excludes packs, ranges, and wrong episodes |
| Season scans stay seasonal | Excludes singles and partial ranges |
| Anchor the series match | Checks meaningful title words |
| Expand release queries | Searches padded, unpadded, ordinal and year forms |
| Provide torrent links | Returns upstream download links/enclosures |
| Annotate Dual Audio | Adds Japanese / English titles and language attributes |

Legacy/Anime defaults enable all eight. New TV/both profiles disable year stripping, Anime pack normalization, query expansion, and Dual Audio annotation. General episode/season/series filtering stays active. Anime profiles clone legacy rules once, then stay independent.

## Walkthrough: A LimeTorrents TV Rule

1. Discover LimeTorrents and create a **TV only** feed selecting it.
2. Select that feed's **Edit rules / Add rule**.
3. Name it **Exclude sample TV releases** and match `SAMPLE`.
4. Set **Search scope = Episodes and seasons**.
5. Set **Indexer = LimeTorrents**, not Nyaa or All indexers.
6. Set **Action = Exclude matching results**, then save.

<figure><a href="{{ '/assets/screenshots/proxy-lime-rule.jpg' | relative_url }}"><img src="{{ '/assets/screenshots/proxy-lime-rule.jpg' | relative_url }}" alt="Complete custom rule editor excluding SAMPLE from LimeTorrents" /></a><figcaption>Current non-Nyaa rule editor. Custom rules start editable; optional locks protect against accidental changes.</figcaption></figure>

| Candidate | Outcome |
| --- | --- |
| Lime: `Example.Show.S01E02.SAMPLE.1080p` | Excluded |
| Lime: `Example.Show.S01E02.1080p` | Eligible for the matching episode request |
| Same SAMPLE title from another source | Unchanged by this source-specific rule |
| Pack during episode search | Rejected before custom rules |

Use specific literal text: SAMPLE can also match legitimate titles containing that word.

## Matching, Scope, and Actions

Matching is a **case-insensitive plain substring of the original title**, not regex. Source and request scope must both match. Custom rules run after built-in parsing/filtering and cannot rescue rejected candidates. Rules run in displayed order; matching exclusions stop the release even if another rule prefers it.

| Scope | Applies when |
| --- | --- |
| Episodes and seasons | Either targeted search type |
| Single episodes only | `season` and `ep` are supplied |
| Season packs only | `season` is supplied without `ep` |

**All indexers in this profile** means only that feed's selected upstreams.

| Action | Example | Effect |
| --- | --- | --- |
| Prefer | Match `[EMBER]` in Anime | Ranks accepted matches first; seeders sort within each group |
| Exclude | Match `SAMPLE` from Lime | Drops the release |
| Replace text | `Example.Show` to `Example Show` | First occurrence in normalized title; original title controls matching |
| Add label | Match `Dual Audio`, label `Preferred Audio` | Appends `[Preferred Audio]`, not audio-stream metadata |

Replacement/label fields appear only when needed. Prefer does not force a download: Sonarr still applies quality, language, custom formats, and rejection rules. Avoid misleading quality/language labels.

## Save and Protect

Rules apply to subsequent requests without redeploying or Sonarr sync. Built-in unlocking saves separately before edits. Profiles persist in `/data/feed-rules/`; exports contain only the selected profile, but your own text can still be private. XML is the response format, not how you author rules: see [Reference]({{ '/reference/' | relative_url }}).
