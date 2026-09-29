# Sonarr-Nyaa Proxy Manager

A mobile-first manager and Sonarr-compatible Nyaa proxy.

## What it does

- Documents the current built-in proxy behavior as locked defaults.
- Lets an operator add, enable, disable, and remove custom rules.
- Persists custom rules to the container's `/data` volume, with a local browser fallback for static previews.
- Exports the combined rule map as JSON for use by a future deployment adapter.
- Includes dark mode by default and a light mode toggle.

## Run locally

Build the container:

```sh
docker build -t ghcr.io/deepdaddyTTV/sonarr-nyaa-proxy-manager:dev .
docker run --rm -p 8787:8787 -v nyaa_proxy_rules:/data ghcr.io/deepdaddyTTV/sonarr-nyaa-proxy-manager:dev
```

Use `http://localhost:8787/api` for Torznab and `http://localhost:8787/manager/` for the manager UI.

## Locked defaults

The UI starts with the proxy's current safety behavior:

1. Strip bracketed years before classification.
2. Normalize season packs to Sonarr-safe `Sxx` titles.
3. Keep episode scans to exact episodes.
4. Keep season scans to packs for the requested season.
5. Anchor release titles to meaningful series words.
6. Expand season search variants.
7. Use direct `.torrent` download URLs.
8. Annotate Dual Audio releases as Japanese and English.

The current custom-rule store is intentionally separate from locked defaults. It preserves operator configuration now and gives the runtime a stable configuration contract for applying additional rule types safely in later releases.
