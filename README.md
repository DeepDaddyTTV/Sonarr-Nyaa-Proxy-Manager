# Sonarr Proxy Manager

Sonarr Proxy Manager is a Dockerized Torznab proxy for Nyaa.si with a small, authenticated rule manager. It normalizes release titles, distinguishes exact episodes from season packs, and returns filtered results to Sonarr.

## What It Does

Sonarr sends indexer searches to the proxy. The proxy searches Nyaa.si, expands season and episode query variants, anchors results to the requested series, and separates episode searches from season-pack searches. Dual Audio releases are announced as Japanese and English. Accepted results use Nyaa's torrent download URL.

The manager at `/manager/` provides a searchable rule library. Built-in rules start locked; click a rule's lock to unlock its name, description, and enabled setting. Custom rules start unlocked and can prefer, exclude, rewrite, or annotate matching releases for all searches, episode scans, or season scans. Settings are stored in `/data/custom-rules.json` on the persistent volume.

When upgrading from the earlier manager, built-in rules are locked once without changing their enabled settings or custom rules. Subsequent lock and unlock choices persist. Dark and light themes use the same icon masks with theme-specific colors.

## Requirements

- Sonarr configured with a Torznab indexer.
- Docker Engine or another OCI-compatible container runtime.
- Network access from the proxy container to Nyaa.si over HTTPS.
- A shared Docker network between Sonarr and the proxy so Sonarr can reach the proxy's TCP port `8787`.
- A persistent `/data` volume for manager settings.
- `AUTH_USERNAME` and `AUTH_PASSWORD` for access to the browser manager. Sonarr's Torznab API remains separate from manager authentication.
- A torrent download client already configured in Sonarr. The proxy finds and describes releases; Sonarr and its download client handle downloads.

No host Python installation or Nyaa account is required. Optional Sonarr URL and API key settings enable series metadata lookup when requests identify a series by TVDB or IMDb ID.

## Container Setup

The public development image is:

```text
ghcr.io/deepdaddyttv/sonarr-proxy-manager:dev
```

Pull it with `docker pull ghcr.io/deepdaddyttv/sonarr-proxy-manager:dev`.

Example Compose service:

```yaml
services:
  sonarr-proxy-manager:
    image: ghcr.io/deepdaddyttv/sonarr-proxy-manager:dev
    restart: unless-stopped
    expose:
      - "8787"
    environment:
      SONARR_URL: ${SONARR_URL:-}
      SONARR_API_KEY: ${SONARR_API_KEY:-}
      PROXY_API_KEY: ${PROXY_API_KEY:-}
      AUTH_USERNAME: ${AUTH_USERNAME:?Set AUTH_USERNAME}
      AUTH_PASSWORD: ${AUTH_PASSWORD:?Set AUTH_PASSWORD}
      AUTH_COOKIE_SECURE: ${AUTH_COOKIE_SECURE:-false}
    volumes:
      - sonarr-proxy-manager-data:/data

volumes:
  sonarr-proxy-manager-data:
```

Connect Sonarr and the proxy to the same Docker network. In Sonarr, add a Torznab indexer with URL `http://sonarr-proxy-manager:8787/api`. If `PROXY_API_KEY` is set, enter the same value in the indexer's API key field. The manager UI is at `http://<proxy-address>:8787/manager/`; publish a host port or configure a private reverse-proxy route only if browser access is needed. The Compose example exposes the port only to its Docker network.

Set both `AUTH_USERNAME` and `AUTH_PASSWORD` to enable the manager. Without them, manager pages and rule APIs remain unavailable while the Torznab `/api` continues to work independently. The session cookie is HTTP-only, same-site, and expires after 12 hours. Set `AUTH_COOKIE_SECURE=true` when the manager is accessed over HTTPS. Use your container manager's secret facility or an untracked environment file for credentials; never commit real credentials.

## Configuration

Settings can be provided as environment variables. Defaults shown here are used when a setting is omitted.

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `8787` | HTTP port inside the container. |
| `RULES_PATH` | `/data/custom-rules.json` | Persistent built-in and custom rule configuration. |
| `NYAA_BASE_URL` | `https://nyaa.si` | Nyaa-compatible index URL. |
| `NYAA_CATEGORY` | `1_2` | Nyaa category filter; `1_2` is Anime - English-translated. |
| `NYAA_FILTER` | `0` | Nyaa filter value. |
| `SONARR_URL` | empty | Sonarr base URL reachable from the proxy container; used for optional series metadata lookup. |
| `SONARR_API_KEY` | empty | Sonarr API key for the optional metadata lookup. |
| `PROXY_API_KEY` | empty | Optional API key required for Torznab `/api` requests. |
| `AUTH_USERNAME` | unset | Username required to sign in to the manager UI. Must be configured with `AUTH_PASSWORD`. |
| `AUTH_PASSWORD` | unset | Password required to sign in to the manager UI. Must be configured with `AUTH_USERNAME`. |
| `AUTH_COOKIE_SECURE` | `false` | Adds the Secure flag to the manager session cookie; enable when accessing the UI over HTTPS. |
| `CACHE_TTL_SECONDS` | `300` | Cache duration for Nyaa and Sonarr responses. |
| `REQUEST_TIMEOUT_SECONDS` | `20` | Outbound request timeout. |
| `SONARR_CONFIG_PATH` | `/app/sonarr_proxy_config.json` | Optional legacy JSON configuration file path. |

## Endpoints

- `/api` - Torznab endpoint to add as an indexer in Sonarr.
- `/manager/` - Authenticated browser UI for built-in defaults and custom rules.
- `/manager/login` - Manager sign-in page.
- `/health` - Basic health response.

## Development

Run the tests and build locally:

```sh
python -m unittest -q test_nyaa_proxy_runtime_patch test_manager_server
docker build -t sonarr-proxy-manager:dev .
```

The GitHub Actions workflow tests the proxy and manager, checks the browser scripts, and publishes the `dev` image plus a commit-specific image to GitHub Container Registry when changes reach `main`.

## License

Distributed under the MIT License. See [LICENSE](LICENSE).
