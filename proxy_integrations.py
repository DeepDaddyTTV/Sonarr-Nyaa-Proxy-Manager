"""Private connection settings, Prowlarr discovery, and owned Sonarr feeds."""

from __future__ import annotations

import copy
import json
import os
import re
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


TV_CATEGORIES = [5020, 5030, 5040, 5045, 5050, 5060, 5080, 5090, 5100, 5110, 5120]
CATEGORY_NAMES = {5030: "SD", 5040: "HD", 5045: "UHD", 5070: "Anime", 5080: "Documentary", 5090: "Other", 5100: "WEB-DL", 5110: "WEBRip", 5120: "HDTV"}
CONNECTION_ENV = {
    "prowlarr": {"url": "PROWLARR_URL", "apiKey": "PROWLARR_API_KEY"},
    "sonarr": {"url": "SONARR_URL", "apiKey": "SONARR_API_KEY"},
    "proxy": {"url": "PROXY_PUBLIC_URL", "apiKey": "PROXY_API_KEY"},
}
ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


def validate_url(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Connection URLs must be strings")
    value = value.strip().rstrip("/")
    if not value:
        return ""
    parts = urllib.parse.urlsplit(value)
    if (parts.scheme not in {"http", "https"} or not parts.hostname or parts.username
            or parts.password or parts.query or parts.fragment or any(char.isspace() for char in value)):
        raise ValueError("Use an HTTP(S) base URL without credentials, query parameters, or fragments")
    return value


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        with open(temporary, "x", encoding="utf-8", opener=lambda name, flags: os.open(name, flags, 0o600)) as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def api_request(base: str, key: str, path: str, *, method: str = "GET", payload: object = None) -> object:
    if not base or not key:
        raise ValueError("Configure the service URL and API key in Settings first")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        base + path, data=body, method=method,
        headers={"X-Api-Key": key, "Accept": "application/json", "Content-Type": "application/json"},
    )
    # Credentials must not follow a redirect to a different host.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            return None

    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=15) as response:
            data = response.read(8_000_001)
            if len(data) > 8_000_000:
                raise ValueError("Service response is too large")
            return json.loads(data) if data else {}
    except urllib.error.HTTPError as error:
        # Never expose a response body or URL: either may contain a secret.
        raise ValueError(f"Service returned HTTP {error.code}; check its URL, API key, and permissions") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ValueError("Could not reach the service; check container networking and its base URL") from None
    except (ValueError, UnicodeDecodeError):
        raise ValueError("Service did not return a valid JSON API response") from None


def category_ids(categories: list) -> list[int]:
    found = set()
    for category in categories:
        if isinstance(category, dict):
            try:
                found.add(int(category["id"]))
            except (KeyError, ValueError, TypeError):
                pass
            found.update(category_ids(category.get("subCategories", category.get("subcategories", [])) or []))
    return sorted(found)


def field_value(indexer: dict, name: str, default=None):
    return next((field.get("value") for field in indexer.get("fields", []) if field.get("name") == name), default)


class IntegrationStore:
    def __init__(self, path: Path, legacy_sources, connection_defaults=None):
        self.path = path
        self.legacy_sources = legacy_sources
        self.lock = threading.RLock()
        self.sync_lock = threading.Lock()
        try:
            self.data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.data = {}
        if not isinstance(self.data, dict):
            raise RuntimeError("Integration configuration must be a JSON object")
        self.data.setdefault("connections", {})
        for service, values in (connection_defaults or {}).items():
            connection = self.data["connections"].setdefault(service, {})
            for field, value in values.items():
                if value and field not in connection:
                    connection[field] = value
        self.data.setdefault("feeds", [])
        self.data.setdefault("discovered", [])
        self.data.setdefault("sonarrMappings", {})
        proxy = self.data["connections"].setdefault("proxy", {})
        if not proxy.get("apiKey"):
            proxy["apiKey"] = secrets.token_hex(24)
            atomic_json(self.path, self.data)
        self.effective()  # Validate declarative environment settings before serving requests.

    def effective(self) -> dict:
        with self.lock:
            result = copy.deepcopy(self.data)
        for service, fields in CONNECTION_ENV.items():
            connection = result["connections"].setdefault(service, {})
            for field, variable in fields.items():
                if os.environ.get(variable):
                    connection[field] = os.environ[variable]
            connection["url"] = validate_url(connection.get("url", ""))
            connection.setdefault("apiKey", "")
        if os.environ.get("PROXY_FEEDS_JSON"):
            try:
                result["feeds"] = self.normalize_feeds(json.loads(os.environ["PROXY_FEEDS_JSON"]), check_sources=False)
            except (ValueError, json.JSONDecodeError) as error:
                raise ValueError(f"Invalid PROXY_FEEDS_JSON: {error}") from None
        return result

    def public_settings(self) -> dict:
        config = self.effective()
        return {
            "connections": {
                service: {
                    "url": config["connections"][service]["url"],
                    "hasApiKey": bool(config["connections"][service]["apiKey"]),
                    "managed": {field: bool(os.environ.get(variable)) for field, variable in fields.items()},
                } for service, fields in CONNECTION_ENV.items()
            },
            "feedsManaged": bool(os.environ.get("PROXY_FEEDS_JSON")),
        }

    def save_settings(self, payload: object) -> dict:
        if not isinstance(payload, dict) or not isinstance(payload.get("connections"), dict):
            raise ValueError("connections must be an object")
        with self.sync_lock, self.lock:
            candidate = copy.deepcopy(self.data)
            for service, incoming in payload["connections"].items():
                if service not in CONNECTION_ENV or not isinstance(incoming, dict):
                    raise ValueError("Unsupported connection")
                target = candidate["connections"].setdefault(service, {})
                for field, value in incoming.items():
                    if field not in CONNECTION_ENV[service]:
                        raise ValueError("Unsupported connection setting")
                    variable = CONNECTION_ENV[service][field]
                    if os.environ.get(variable):
                        if value not in ("", None, os.environ[variable]):
                            raise ValueError(f"{variable} is managed by the environment")
                        continue
                    if field == "url":
                        target[field] = validate_url(value)
                    elif value is None:
                        if service == "proxy":
                            raise ValueError("The proxy feed API key cannot be empty")
                        target[field] = ""
                    elif not isinstance(value, str) or len(value) > 512 or any(ord(char) < 32 for char in value):
                        raise ValueError("API keys must be strings without control characters")
                    elif value:
                        target[field] = value
            if candidate["connections"].get("prowlarr") != self.data["connections"].get("prowlarr"):
                candidate["discovered"] = []
            atomic_json(self.path, candidate)
            self.data = candidate
        return self.public_settings()

    def test_connection(self, service: str) -> dict:
        if service not in {"prowlarr", "sonarr"}:
            raise ValueError("Choose Prowlarr or Sonarr")
        connection = self.effective()["connections"][service]
        version = "v1" if service == "prowlarr" else "v3"
        status = api_request(connection["url"], connection["apiKey"], f"/api/{version}/system/status")
        if not isinstance(status, dict) or not status.get("version"):
            raise ValueError("Service response is not a supported Arr API")
        return {"service": service, "version": status["version"], "connected": True}

    def discover(self) -> list[dict]:
        config = self.effective()
        connection = config["connections"]["prowlarr"]
        indexers = api_request(connection["url"], connection["apiKey"], "/api/v1/indexer")
        if not isinstance(indexers, list):
            raise ValueError("Prowlarr did not return an indexer list")
        found = []
        proxy_url = config["connections"]["proxy"]["url"]
        for item in indexers:
            if not isinstance(item, dict) or item.get("protocol") not in {"torrent", 1} or not item.get("enable", True) or not item.get("supportsSearch", True):
                continue
            base = str(field_value(item, "baseUrl", "") or "").rstrip("/")
            path = str(field_value(item, "apiPath", "") or "")
            name = str(item.get("name") or "")[:64]
            normalized_name = re.sub(r"[^a-z0-9]+", " ", name.casefold()).strip()
            if (normalized_name.startswith(("sonarr proxy", "nyaa season proxy", "sonarr nyaa proxy")) or "/feeds/" in base + path
                    or (proxy_url and base == proxy_url)):
                continue
            indexer_id = item.get("id")
            if not isinstance(indexer_id, int) or isinstance(indexer_id, bool) or indexer_id <= 0:
                continue
            caps = item.get("capabilities") or {}
            found.append({
                "id": f"prowlarr-{indexer_id}", "name": name or f"Indexer {indexer_id}",
                "prowlarrId": indexer_id, "categories": category_ids(caps.get("categories", [])),
                "searchParams": caps.get("searchParams", ["q"]),
                "tvSearchParams": caps.get("tvSearchParams", ["q", "season", "ep"]),
            })
        with self.lock:
            if self.effective()["connections"]["prowlarr"] != connection:
                raise ValueError("Prowlarr settings changed during discovery; try again")
            candidate = copy.deepcopy(self.data)
            candidate["discovered"] = found
            candidate["discoveredUrl"] = connection["url"]
            atomic_json(self.path, candidate)
            self.data = candidate
        return self.public_sources()

    def sources(self) -> list[dict]:
        config = self.effective()
        sources = copy.deepcopy(self.legacy_sources())
        connection = config["connections"]["prowlarr"]
        if connection["url"] and connection["apiKey"] and config.get("discoveredUrl") == connection["url"]:
            for entry in config["discovered"]:
                if entry["id"] in {source["id"] for source in sources}:
                    continue
                sources.append({**entry, "type": "torznab", "url": f"{connection['url']}/{entry['prowlarrId']}/api", "api_key": connection["apiKey"]})
        return sources

    def public_sources(self) -> list[dict]:
        return [{"id": source["id"], "name": source["name"], "categories": source.get("categories", []), "origin": "Prowlarr" if "prowlarrId" in source else "Compose / built-in"} for source in self.sources()]

    def normalize_feeds(self, feeds: object, *, check_sources: bool = True) -> list[dict]:
        if not isinstance(feeds, list) or len(feeds) > 30:
            raise ValueError("feeds must be an array of at most 30 feeds")
        known = {source["id"] for source in self.sources()} if check_sources else None
        normalized = []
        seen = set()
        for feed in feeds:
            if not isinstance(feed, dict):
                raise ValueError("Each feed must be an object")
            feed_id = feed.get("id", "")
            name = feed.get("name", "")
            mode = feed.get("mode", "anime")
            source_ids = feed.get("sourceIds", [])
            enabled = feed.get("enabled", True)
            if not isinstance(feed_id, str) or not ID_PATTERN.fullmatch(feed_id) or feed_id in seen:
                raise ValueError("Feed ids must be unique letters, digits, underscores, or hyphens")
            if not isinstance(name, str) or not name.strip() or len(name) > 64:
                raise ValueError("Feed names must contain 1 to 64 characters")
            if mode not in {"anime", "tv", "both"} or not isinstance(enabled, bool):
                raise ValueError("Feed mode must be anime, tv, or both, with a boolean enabled setting")
            if not isinstance(source_ids, list) or not 1 <= len(source_ids) <= 20 or any(not isinstance(value, str) or not ID_PATTERN.fullmatch(value) for value in source_ids):
                raise ValueError("Select 1 to 20 upstream indexers for each feed")
            if known is not None and any(value not in known for value in source_ids):
                # An existing unavailable source remains visible, but cannot be added to a new feed.
                previous = next((value for value in self.effective()["feeds"] if value["id"] == feed_id), {})
                if any(value not in known and value not in previous.get("sourceIds", []) for value in source_ids):
                    raise ValueError("Discover Prowlarr indexers before selecting them")
            categories = feed.get("tvCategories", TV_CATEGORIES)
            if not isinstance(categories, list) or not categories or any(isinstance(value, bool) or not isinstance(value, int) or value not in TV_CATEGORIES for value in categories):
                raise ValueError("TV categories must be specific TV subcategories, not parent 5000 or Anime 5070")
            normalized.append({"id": feed_id, "name": name.strip(), "mode": mode, "sourceIds": list(dict.fromkeys(source_ids)), "enabled": enabled, "tvCategories": sorted(set(categories))})
            seen.add(feed_id)
        return normalized

    def save_feeds(self, payload: object) -> list[dict]:
        if os.environ.get("PROXY_FEEDS_JSON"):
            raise ValueError("PROXY_FEEDS_JSON manages feeds; remove it to edit feeds in the UI")
        with self.sync_lock, self.lock:
            feeds = self.normalize_feeds(payload)
            candidate = copy.deepcopy(self.data)
            candidate["feeds"] = feeds
            atomic_json(self.path, candidate)
            self.data = candidate
        return self.public_feeds()

    def feeds(self) -> list[dict]:
        return self.effective()["feeds"]

    def public_feeds(self) -> list[dict]:
        config = self.effective()
        base = config["connections"]["proxy"]["url"]
        known = {source["id"] for source in self.sources()}
        return [{**feed, "apiPath": f"/feeds/{feed['id']}/api", "url": base, "unavailableSources": [value for value in feed["sourceIds"] if value not in known]} for feed in config["feeds"]]

    def sync_sonarr(self) -> dict:
        # The lock prevents two requests from creating the same virtual indexer.
        with self.sync_lock:
            config = self.effective()
            sonarr = config["connections"]["sonarr"]
            proxy = config["connections"]["proxy"]
            if not proxy["url"]:
                raise ValueError("Set the proxy base URL reachable from Sonarr first")
            call = lambda path, **kwargs: api_request(sonarr["url"], sonarr["apiKey"], path, **kwargs)
            existing = call("/api/v3/indexer")
            schemas = call("/api/v3/indexer/schema")
            if not isinstance(existing, list) or not isinstance(schemas, list):
                raise ValueError("Sonarr did not return an indexer list and schema")
            template = next((value for value in schemas if value.get("implementation") == "Torznab"), None)
            if template is None:
                raise ValueError("Sonarr has no Torznab indexer schema")
            outcome = []
            namespace = sonarr["url"]
            with self.lock:
                owned = copy.deepcopy(self.data.get("sonarrMappings", {}).get(namespace, {}))
            for feed in config["feeds"]:
                path = f"/feeds/{feed['id']}/api"
                mapping = owned.get(feed["id"], {})
                previous = next((value for value in existing if value.get("id") == mapping.get("id")), None)
                if previous is not None:
                    if (field_value(previous, "baseUrl") != mapping.get("baseUrl")
                            or field_value(previous, "apiPath") != path or previous.get("implementation") != "Torznab"):
                        raise ValueError(f"Ownership of {feed['name']} changed in Sonarr; refusing to overwrite it")
                else:
                    conflicts = [value for value in existing if value.get("implementation") == "Torznab"
                                 and field_value(value, "baseUrl") == proxy["url"] and field_value(value, "apiPath") == path
                                 and field_value(value, "apiKey") != proxy["apiKey"]]
                    if conflicts:
                        raise ValueError(f"An unowned Sonarr entry already uses feed {feed['id']}; refusing to duplicate or overwrite it")
                    candidates = [value for value in existing if value.get("implementation") == "Torznab"
                                  and field_value(value, "baseUrl") == proxy["url"] and field_value(value, "apiPath") == path
                                  and field_value(value, "apiKey") == proxy["apiKey"]]
                    if len(candidates) > 1:
                        raise ValueError(f"Multiple Sonarr entries already use feed {feed['id']}; resolve the duplicate")
                    previous = candidates[0] if candidates else None
                if previous is None and not feed["enabled"]:
                    continue
                if feed["enabled"] and any(value not in {source["id"] for source in self.sources()} for value in feed["sourceIds"]):
                    raise ValueError(f"{feed['name']} has unavailable upstreams; rediscover Prowlarr first")
                entry = copy.deepcopy(previous if previous is not None else template)
                entry.update(name=feed["name"], enableRss=False, enableAutomaticSearch=feed["enabled"], enableInteractiveSearch=feed["enabled"])
                values = {"baseUrl": proxy["url"], "apiPath": path, "apiKey": proxy["apiKey"],
                          "categories": feed["tvCategories"] if feed["mode"] in {"tv", "both"} else [],
                          "animeCategories": [5070] if feed["mode"] in {"anime", "both"} else [],
                          "animeStandardFormatSearch": True, "additionalParameters": ""}
                for field in entry.get("fields", []):
                    if field.get("name") in values:
                        field["value"] = values[field["name"]]
                if previous is None:
                    entry.pop("id", None)
                try:
                    saved = call(f"/api/v3/indexer/{previous['id']}" if previous else "/api/v3/indexer", method="PUT" if previous else "POST", payload=entry)
                except ValueError:
                    raise ValueError(f"Could not register {feed['name']}; verify Sonarr can reach the proxy URL and its upstreams. Earlier feeds may have synced; retry is safe.") from None
                if not isinstance(saved, dict) or not isinstance(saved.get("id"), int):
                    raise ValueError("Sonarr returned an invalid saved indexer")
                owned[feed["id"]] = {"id": saved["id"], "baseUrl": proxy["url"]}
                # Persist each successful registration so retries cannot create duplicates.
                with self.lock:
                    candidate = copy.deepcopy(self.data)
                    candidate.setdefault("sonarrMappings", {}).setdefault(namespace, {})[feed["id"]] = owned[feed["id"]]
                    atomic_json(self.path, candidate)
                    self.data = candidate
                existing = [value for value in existing if value.get("id") != saved["id"]] + [saved]
                outcome.append({"feedId": feed["id"], "name": feed["name"], "sonarrId": saved["id"], "action": "updated" if previous else "created"})
            return {"entries": outcome, "message": "Only this manager's feeds were synchronized. Existing Prowlarr entries were not changed."}
