# Sonarr Proxy Manager

[Project guide / wiki](https://deepdaddyttv.github.io/Sonarr-Proxy-Manager/) · [Buy Me a Coffee](https://buymeacoffee.com/deepdaddyttv)

Sonarr Proxy Manager is a Dockerized Torznab proxy for Sonarr. It searches Nyaa by default and can query additional Torznab-compatible indexers configured in Compose. It expands searches, normalizes release titles, keeps episode results separate from season packs, and provides an authenticated web manager for built-in and custom matching rules.

## What It Does

Sonarr sends a Torznab search to `/api`. The proxy builds bounded query variants, searches Nyaa and any configured Torznab upstreams, checks that results belong to the requested series and season, and returns one RSS 2.0 feed containing the merged results. Episode searches return only the requested episode; season searches filter out single episodes and partial ranges. Dual Audio releases are labeled as Japanese and English in both the title and Torznab language attributes.

The browser rule manager is served at `/manager/`. Built-in rules are enabled and locked by default. A lock protects a rule's editable settings in the UI; unlock a rule to change its enabled state or display name and description. The actual matching behavior for each built-in rule is implemented by the proxy. Custom rules can prefer, exclude, rewrite, or annotate matching releases for all searches, episode searches, or season searches, and can target one configured indexer or all of them. Rule settings persist in `/data/custom-rules.json`.

## Requirements

- Sonarr configured with a Torznab indexer.
- Docker Engine or another OCI-compatible container runtime.
- Outbound HTTPS access from the container to Nyaa.si and any configured upstream indexers.
- A Docker network shared by Sonarr and this container.
- A persistent `/data` volume.
- `AUTH_USERNAME` and `AUTH_PASSWORD` for the browser manager.
- A torrent download client already configured in Sonarr. This proxy finds and describes releases; Sonarr and its download client handle downloads.

No host Python installation or Nyaa account is required. Optional Sonarr URL and API key settings enable series metadata lookup when requests identify a series by TVDB or IMDb ID.

## Quick Start

The project publishes a rolling `stable` image as well as `dev` and commit-specific images. Use `stable` for normal installs; `dev` is available for testing. The personal development stack for this project may use `dev` independently.

Create a Docker network shared with Sonarr if you do not already have one:

```sh
docker network create sonarr-net
```

Attach the Sonarr container to that network, then save this as `compose.yaml`:

```yaml
services:
  sonarr-proxy-manager:
    image: ghcr.io/deepdaddyttv/sonarr-proxy-manager:stable
    restart: unless-stopped
    ports:
      - "127.0.0.1:8787:8787"
    environment:
      SONARR_URL: ${SONARR_URL:-}
      SONARR_API_KEY: ${SONARR_API_KEY:-}
      PROXY_API_KEY: ${PROXY_API_KEY:-}
      UPSTREAM_INDEXERS_JSON: "${UPSTREAM_INDEXERS_JSON:-[]}"
      AUTH_USERNAME: ${AUTH_USERNAME:?Set AUTH_USERNAME}
      AUTH_PASSWORD: ${AUTH_PASSWORD:?Set AUTH_PASSWORD}
      AUTH_COOKIE_SECURE: ${AUTH_COOKIE_SECURE:-false}
    volumes:
      - sonarr-proxy-manager-data:/data
    networks:
      - sonarr-net

volumes:
  sonarr-proxy-manager-data:

networks:
  sonarr-net:
    external: true
```

Create an untracked `.env` file beside the Compose file:

```dotenv
AUTH_USERNAME=proxy-admin
AUTH_PASSWORD=replace-with-a-long-unique-password
AUTH_COOKIE_SECURE=false
PROXY_API_KEY=
SONARR_URL=
SONARR_API_KEY=
UPSTREAM_INDEXERS_JSON='[{"id":"prowlarr-anime","name":"Prowlarr Anime","url":"http://prowlarr:9696/1/api","api_key":"replace-with-prowlarr-api-key","categories":["5000","5070"]}]'
```

Nyaa is always available as the built-in source. The optional JSON array adds Torznab-compatible upstreams; use the API URL and key shown by that indexer (for example, copy the Torznab URL from Prowlarr and make sure its hostname is reachable on the proxy's Docker network). `id` must be unique and use letters, numbers, `_` or `-`; `name` is shown in the rule editor. `categories` is optional and limits the upstream query to Torznab category IDs. After changing the Compose environment, recreate the container; the configured names then appear in the custom-rule Indexer selector. Indexer credentials remain server-side and are never returned by the manager API. They are present in the container environment, so keep the Compose file and `.env` private.

Start the service with `docker compose up -d`. The manager is available locally at `http://127.0.0.1:8787/manager/`. Do not expose the manager publicly. If you put it behind HTTPS, set `AUTH_COOKIE_SECURE=true` and use a private, access-controlled route.

### Connect Sonarr

Add the proxy once as an indexer in Sonarr. Upstream indexers are searched behind this single endpoint:

1. Open **Settings → Indexers → Add Indexer → Torrent → Torznab (Custom)**.
2. Set the name to `Sonarr Proxy Manager`.
3. Set the URL to `http://sonarr-proxy-manager:8787/api`. Use the proxy's reachable host and port instead if Sonarr is not on the shared Docker network.
4. Leave the API key empty unless `PROXY_API_KEY` is set; if set, enter that exact value.
5. Select **TV** and/or **Anime** (`5070`) categories supported by your Sonarr version, then use **Test** and **Save**.
6. Make sure a torrent download client is configured in Sonarr. The proxy returns releases; Sonarr and its download client perform the download.

| Setting | Value |
| --- | --- |
| URL | `http://sonarr-proxy-manager:8787/api` |
| API key | Leave blank unless `PROXY_API_KEY` is set; otherwise use that value. |
| Categories | TV / Anime, if Sonarr asks for categories. |

The proxy advertises standard TV categories as well as Anime. Nyaa remains restricted to its configured category (`1_2` by default); other upstreams can use their own Torznab category IDs in `UPSTREAM_INDEXERS_JSON`. Sonarr and the proxy must share `sonarr-net` for the container hostname above to resolve. Manager login credentials and `PROXY_API_KEY` are separate: the former protects the browser UI, while the latter optionally protects Torznab requests.

### Add More Indexers

Use `UPSTREAM_INDEXERS_JSON` to add any upstream that exposes a Torznab API, including individual Prowlarr or Jackett indexer endpoints. This is not a raw-site scraper for arbitrary API formats; the upstream must accept standard Torznab `tvsearch` requests. Example with two sources:

```json
[
  {
    "id": "prowlarr-anime",
    "name": "Prowlarr Anime",
    "url": "http://prowlarr:9696/1/api",
    "api_key": "YOUR_PROWLARR_API_KEY",
    "categories": ["5000", "5070"]
  },
  {
    "id": "jackett-tv",
    "name": "Jackett TV",
    "url": "http://jackett:9117/api/v2.0/indexers/example/results/torznab/api",
    "api_key": "YOUR_JACKETT_API_KEY",
    "categories": ["5000"]
  }
]
```

Each source must be reachable from the proxy container. After recreating the proxy with the updated JSON, choose **All indexers** or a specific source when creating or editing a custom rule. Existing rules migrate to **All indexers** automatically. For example, an exclude rule matching `Judas` can be limited to `Prowlarr Anime` without affecting a Judas release returned by Nyaa or another source.

## Built-In Rules

These eight rules are enabled and locked by default. Unlocking a built-in rule permits changing its manager settings; it does not replace or redefine the matching algorithm described here.

| Rule | Default behavior |
| --- | --- |
| Strip release years | Removes bracketed years before classification so a year such as `[2024]` is not mistaken for an episode number. |
| Normalize season packs | Recognizes `Season 1`, `S01`, and ordinal season forms, then rewrites accepted season titles to Sonarr-safe `Sxx` form. |
| Episode scans stay episodic | For a request with both `season` and `ep`, keeps only the exact matching `SxxExx`; season packs and episode ranges are excluded. |
| Season scans stay seasonal | For a request with `season` but no `ep`, excludes single episodes and partial ranges while keeping matching season packs. |
| Anchor the series match | Requires meaningful query words to match the release title, reducing accidental substring matches for a different series. |
| Expand release queries | Tries padded, unpadded, ordinal, and year-aware season/episode query forms to find more release groups. |
| Provide torrent links | Uses each upstream's download URL in the Torznab `link` and `enclosure`. |
| Annotate Dual Audio | Adds Japanese and English to Dual Audio titles and emits Torznab `language` attributes with those names. |

Weekly episode searches are not a goal of this proxy: the base behavior focuses on exact episode results and season packs.

## Add a Custom Rule

Sign in to `/manager/`, open **Custom rules**, and select **Add rule**. Custom rules are editable by default. Enter a name, the text to match, a scope, an indexer target, and an action:

| Action | Effect |
| --- | --- |
| Prefer | Moves matching results ahead of other accepted results; seeders order results within each group. |
| Exclude | Removes a matching result from the feed. |
| Rewrite | Replaces the first case-insensitive occurrence of the match text in the normalized title with the replacement value. |
| Annotate | Appends the supplied value in brackets to the normalized title. |

Matching is a case-insensitive substring check against the original release title. Choose **Episodes and seasons**, **Episode searches**, or **Season searches**, then select **All indexers** or one configured upstream and save. The rule manager writes the JSON configuration to the persistent data volume; you do not need to edit XML or hand-write rule JSON.

For example, to put Judas season packs from only one source first, add a rule with match `Judas`, scope **Season searches**, select that indexer, and choose **Prefer**. A matching Judas pack from the selected source will be listed before other accepted results, even if they have more seeders. To remove a noisy release group from just one source, choose **Exclude** and select the same indexer; choose **All indexers** to apply it across sources.

## Torznab Requests and XML Examples

The proxy accepts query-string requests and returns XML. XML is the response format; XML is not the format for adding rules.

Capabilities request:

```text
GET /api?t=caps
```

Example episode search for season 1, episode 6:

```text
GET /api?t=tvsearch&q=Moonrise&season=1&ep=6
```

Example season search for season 1 (omit `ep`):

```text
GET /api?t=tvsearch&q=Moonrise&season=1
```

If `PROXY_API_KEY` is configured, append `&apikey=YOUR_PROXY_API_KEY`. Sonarr also supplies TVDB/IMDb identifiers when available. The proxy advertises `q`, `season`, `ep`, `tvdbid`, and `imdbid` in its Torznab capabilities.

The following abbreviated feed item illustrates an accepted Nyaa episode result after title normalization and Dual Audio annotation. Values such as the Nyaa ID, hash, size, and date are illustrative:

```xml
<rss version="2.0"
     xmlns:atom="http://www.w3.org/2005/Atom"
     xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <title>Sonarr Proxy Manager</title>
    <description>Nyaa results with Sonarr-friendly season-pack titles</description>
    <item>
      <title>[Judas] Moonrise S01E06 1080p [Dual Audio] [Japanese English]</title>
      <guid isPermaLink="true">https://nyaa.si/view/1234567</guid>
      <link>https://nyaa.si/download/1234567.torrent</link>
      <comments>https://nyaa.si/view/1234567</comments>
      <pubDate>Mon, 01 Jun 2026 12:00:00 +0000</pubDate>
      <size>1500000000</size>
      <description>[Judas] Moonrise S01E06 1080p [Dual Audio] [Japanese English] | original: [Judas] Moonrise Season 1 - 06 1080p [Dual Audio]</description>
      <enclosure url="https://nyaa.si/download/1234567.torrent"
                 length="1500000000"
                 type="application/x-bittorrent" />
      <torznab:attr name="category" value="5070" />
      <torznab:attr name="seeders" value="42" />
      <torznab:attr name="peers" value="50" />
      <torznab:attr name="grabs" value="120" />
      <torznab:attr name="infohash" value="0123456789abcdef0123456789abcdef01234567" />
      <torznab:attr name="language" value="Japanese" />
      <torznab:attr name="language" value="English" />
    </item>
  </channel>
</rss>
```

For a season search, the same normalization turns a full-season title such as `[EMBER] Moonrise Season 1 [1080p] [Dual Audio]` into a Sonarr-safe title containing `S01`; single episodes and partial episode ranges are filtered before they reach the feed. A direct torrent link is emitted by default. The feed's Torznab category is Anime (`5070`), and Dual Audio language attributes use the language names `Japanese` and `English`.

For clarity, a season-pack result is a separate response to a request without `ep`; it is not mixed into the episode response above. An abbreviated season-pack item looks like this:

```xml
<item xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <title>[EMBER] Moonrise S01 [1080p] [Dual Audio] [Japanese English]</title>
  <guid isPermaLink="true">https://nyaa.si/view/1234568</guid>
  <link>https://nyaa.si/download/1234568.torrent</link>
  <comments>https://nyaa.si/view/1234568</comments>
  <pubDate>Mon, 01 Jun 2026 12:05:00 +0000</pubDate>
  <size>9000000000</size>
  <description>[EMBER] Moonrise S01 [1080p] [Dual Audio] [Japanese English] | original: [EMBER] Moonrise Season 1 [1080p] [Dual Audio]</description>
  <enclosure url="https://nyaa.si/download/1234568.torrent"
             length="9000000000"
             type="application/x-bittorrent" />
  <torznab:attr name="category" value="5070" />
  <torznab:attr name="seeders" value="18" />
  <torznab:attr name="peers" value="23" />
  <torznab:attr name="grabs" value="75" />
  <torznab:attr name="infohash" value="89abcdef0123456789abcdef0123456789abcdef" />
  <torznab:attr name="language" value="Japanese" />
  <torznab:attr name="language" value="English" />
</item>
```

## Configuration

Environment variables (defaults apply when omitted):

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `8787` | HTTP port inside the container. |
| `RULES_PATH` | `/data/custom-rules.json` | Persistent built-in and custom rule configuration. |
| `NYAA_BASE_URL` | `https://nyaa.si` | Nyaa base URL used for RSS searches. |
| `NYAA_CATEGORY` | `1_2` | Nyaa category filter; `1_2` is Anime - English-translated. |
| `NYAA_FILTER` | `0` | Nyaa filter value. |
| `UPSTREAM_INDEXERS_JSON` | `[]` | JSON array of additional Torznab upstreams. Each entry needs a unique `id`, display `name`, API `url`, and optionally `api_key` and `categories`. |
| `SONARR_URL` | empty | Sonarr base URL reachable from the proxy; used for optional series metadata lookup. |
| `SONARR_API_KEY` | empty | Sonarr API key for optional metadata lookup. |
| `PROXY_API_KEY` | empty | Optional API key required for Torznab `/api` requests. |
| `AUTH_USERNAME` | unset | Manager sign-in username; configure with `AUTH_PASSWORD`. |
| `AUTH_PASSWORD` | unset | Manager sign-in password; configure with `AUTH_USERNAME`. |
| `AUTH_COOKIE_SECURE` | `false` | Set `true` when accessing the manager over HTTPS. |
| `CACHE_TTL_SECONDS` | `300` | Cache duration for indexer and Sonarr responses. |
| `REQUEST_TIMEOUT_SECONDS` | `20` | Outbound request timeout. |
| `SONARR_CONFIG_PATH` | `/app/sonarr_proxy_config.json` | Optional legacy JSON configuration file path. |

The manager session cookie is HTTP-only, same-site, and expires after 12 hours. Use Docker secrets or an untracked environment file for credentials; never commit real credentials.

## Endpoints

| Path | Purpose |
| --- | --- |
| `/api` | Torznab endpoint to add as an indexer in Sonarr. |
| `/api?t=caps` | Torznab capabilities response. |
| `/manager/` | Authenticated rule manager. |
| `/manager/login` | Manager sign-in page. |
| `/health` | Basic health response. |

## Development and Images

Run the tests and build locally:

```sh
python -m unittest -q test_nyaa_proxy_runtime_patch test_manager_server
docker build -t sonarr-proxy-manager:dev .
```

Every successful push to `main` runs tests, checks the manager scripts, and publishes these GitHub Container Registry tags:

- `ghcr.io/deepdaddyttv/sonarr-proxy-manager:stable`
- `ghcr.io/deepdaddyttv/sonarr-proxy-manager:dev`
- `ghcr.io/deepdaddyttv/sonarr-proxy-manager:sha-<commit>`

`stable` and `dev` are rolling tags for the main-branch build; use the commit-specific tag when you need to pin an exact image.

## License

Distributed under the MIT License. See [LICENSE](LICENSE).
