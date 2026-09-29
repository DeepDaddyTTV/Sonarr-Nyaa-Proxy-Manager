# Sonarr-Nyaa Proxy Manager

A small Torznab-compatible proxy for Nyaa.si, with a web interface for reviewing built-in behavior and managing custom rule data.

## What It Does

Sonarr sends release searches to this service. The proxy searches Nyaa.si and reshapes its results to make anime season packs and episodes easier for Sonarr to identify. Its built-in behavior handles season naming variants, separates season-pack and exact-episode results, matches meaningful series-title words, and adds Japanese and English language metadata to releases marked Dual Audio. When Nyaa provides an info hash, the proxy prefers a magnet link and falls back to the torrent download URL when it does not.

The manager is available at `/manager/`. It shows the built-in rules as locked defaults and lets operators save, enable, disable, remove, and export custom rule definitions. Custom rules are stored in `/data/custom-rules.json` on the persistent `/data` volume. **Custom rules are currently saved and exported, but are not yet applied to release searches.**

## Requirements

- Sonarr, with permission to add a Torznab indexer.
- Docker Engine or another OCI-compatible container runtime.
- Network access from the proxy container to Nyaa.si over HTTPS, and network access from Sonarr to the proxy on container TCP port `8787`.
- A persistent volume mounted at `/data` if custom rule data should survive container replacement.
- A torrent download client already configured in Sonarr to download releases. This proxy finds and describes releases; Sonarr and its download client handle downloads.

No Python installation or Nyaa account is required on the host. The image contains the Python runtime. Sonarr's URL and API key are optional and only used when the proxy needs to look up series metadata from Sonarr identifiers.

## Container Setup

Use the public development image:

```text
ghcr.io/deepdaddyttv/sonarr-nyaa-proxy-manager:dev
```

Pull it with `docker pull ghcr.io/deepdaddyttv/sonarr-nyaa-proxy-manager:dev`.

Example Compose service:

```yaml
services:
  nyaa-proxy:
    image: ghcr.io/deepdaddyttv/sonarr-nyaa-proxy-manager:dev
    restart: unless-stopped
    expose:
      - "8787"
    environment:
      SONARR_URL: ${SONARR_URL:-}
      SONARR_API_KEY: ${SONARR_API_KEY:-}
      PROXY_API_KEY: ${PROXY_API_KEY:-}
    volumes:
      - nyaa-proxy-data:/data

volumes:
  nyaa-proxy-data:
```

Connect the proxy and Sonarr to the same Docker network. In Sonarr, add a Torznab indexer with URL `http://nyaa-proxy:8787/api`. If `PROXY_API_KEY` is set, enter the same value in the indexer's API key field. The manager UI is at `http://<proxy-address>:8787/manager/`; choose a host port mapping only if you need browser access to it. The example above exposes the container port only to its Docker network and does not publish a host port.

Keep the manager UI on a trusted network. The Torznab `PROXY_API_KEY` protects `/api`; it does not add authentication to the manager UI or its rule-writing endpoint.

## Configuration

Settings can be provided as environment variables. Defaults shown here are used when a setting is omitted.

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `8787` | HTTP port inside the container. |
| `RULES_PATH` | `/data/custom-rules.json` | File used to persist custom rule definitions. |
| `NYAA_BASE_URL` | `https://nyaa.si` | Nyaa-compatible index URL. |
| `NYAA_CATEGORY` | `1_2` | Nyaa category filter; `1_2` is Anime - English-translated. |
| `NYAA_FILTER` | `0` | Nyaa filter value. |
| `SONARR_URL` | empty | Sonarr base URL reachable from the proxy container; used for series metadata lookup. |
| `SONARR_API_KEY` | empty | Sonarr API key for the optional metadata lookup. |
| `PROXY_API_KEY` | empty | Optional API key required for Torznab `/api` requests. |
| `CACHE_TTL_SECONDS` | `300` | Cache duration for Nyaa and Sonarr responses. |
| `REQUEST_TIMEOUT_SECONDS` | `20` | Outbound request timeout. |
| `SONARR_CONFIG_PATH` | `/app/sonarr_proxy_config.json` | Optional legacy JSON configuration file path. |

Do not put real API keys in a public Compose file or commit them to source control. Use your container manager's secret or environment-variable facility.

## Endpoints

- `/api` - Torznab endpoint to add as an indexer in Sonarr.
- `/manager/` - Browser UI for built-in defaults and custom rule data.
- `/health` - Basic health response.

## Development

Build locally with Docker:

```sh
docker build -t sonarr-nyaa-proxy-manager:dev .
```

The GitHub Actions workflow publishes the `dev` image and a commit-specific image to GitHub Container Registry on pushes to `main`.

## License

Distributed under the MIT License. See [LICENSE](LICENSE).
