"""Run the Sonarr-compatible proxy and serve the rule manager UI."""

from __future__ import annotations

import json
import hashlib
import hmac
import mimetypes
import os
import re
import secrets
import time
import copy
import threading
from http.cookies import CookieError, SimpleCookie
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import nyaa_season_proxy as proxy
from nyaa_proxy_runtime_patch import install
from proxy_integrations import IntegrationStore, atomic_json


ROOT = Path(__file__).resolve().parent
SCHEMA_VERSION = 4
RULES_PATH = Path(os.environ.get("RULES_PATH", "/data/custom-rules.json"))
INTEGRATIONS = None
LEGACY_SOURCES = proxy.configured_indexers
RULES_LOCK = threading.RLock()
AUTH_USERNAME = os.environ.get("AUTH_USERNAME")
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD")
if (AUTH_USERNAME is None) != (AUTH_PASSWORD is None) or (
    AUTH_USERNAME is not None and (not AUTH_USERNAME or not AUTH_PASSWORD)
):
    raise RuntimeError("AUTH_USERNAME and AUTH_PASSWORD must be configured together")

AUTH_ENABLED = bool(AUTH_USERNAME and AUTH_PASSWORD)
AUTH_COOKIE_SECURE = os.environ.get("AUTH_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
SESSION_COOKIE = "SonarrProxyManagerSession"
SESSION_TTL_SECONDS = 12 * 60 * 60
SESSION_SIGNING_KEY = secrets.token_bytes(32)
RULE_CATALOG = {
    "year-hygiene": ("Strip release years", "title rewrite", "Removes bracketed years before classification so release years are not mistaken for episode numbers."),
    "season-classification": ("Normalize season packs", "season pack", "Recognizes Season 1, S01, and ordinal seasons, then rewrites accepted packs to a Sonarr-safe Sxx title."),
    "episode-isolation": ("Episode scans stay episodic", "episode filter", "Only returns the exact requested SxxExx release for an episode search. Packs and episode ranges are excluded."),
    "season-isolation": ("Season scans stay seasonal", "season filter", "Excludes single episodes and partial ranges from season searches while keeping full packs for the requested season."),
    "series-anchor": ("Anchor the series match", "series safety", "Requires meaningful title words to match, reducing substring results for a different show."),
    "query-expansion": ("Expand release queries", "search strategy", "Searches padded, unpadded, ordinal, and year-aware season forms to retain additional release-group results."),
    "direct-torrent": ("Provide torrent links", "delivery", "Uses the upstream indexer's download link for accepted releases."),
    "dual-audio": ("Annotate Dual Audio", "languages", "Adds Japanese and English to Dual Audio titles and Torznab metadata so Sonarr sees both languages."),
}
STATIC_FILES = {
    "/manager/styles.css": "styles.css",
    "/manager/auth.js": "auth.js",
    "/manager/site-icon.js": "site-icon.js",
}
ICON_FILES = {
    name: f"assets/icons/{name}"
    for name in (
        "002-filter.png", "007-trash-1.png", "020-pen.png", "033-lock.png",
        "034-lock-1.png", "036-login.png", "069-file.png", "076-construction.png",
        "065-cogwheel.png", "050-dark.png", "sun.png", "electronic.png",
    )
}


def default_rule_settings() -> dict[str, dict]:
    return {
        rule_id: {
            "enabled": True,
            "locked": True,
            "name": name,
            "description": description,
        }
        for rule_id, (name, _kind, description) in RULE_CATALOG.items()
    }


def _normalize_custom_rule(rule: dict, *, strict: bool) -> dict | None:
    actions = {"exclude", "prefer", "rewrite", "annotate"}
    scopes = {"all", "episodes", "seasons"}
    if strict and any(not isinstance(rule.get(key), str) for key in ("id", "name", "match", "action", "scope")):
        raise ValueError("Each custom rule needs string id, name, match, action, and scope fields")
    rule_id = str(rule.get("id") or secrets.token_hex(12))[:64]
    name = str(rule.get("name") or "").strip()[:64]
    match = str(rule.get("match") or "").strip()[:120]
    action = str(rule.get("action") or "exclude")
    scope = str(rule.get("scope") or "all")
    value = str(rule.get("value") or "").strip()[:120]
    indexer = str(rule.get("indexer") or "all").strip()[:64]
    enabled = rule.get("enabled", True)
    locked = rule.get("locked", False)
    if action == "keep":
        action = "prefer"
    if strict:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", rule_id):
            raise ValueError("Rule ids may contain letters, numbers, underscores, and hyphens")
        if not name or not match:
            raise ValueError("Custom rules need a name and a title match")
        if action not in actions or scope not in scopes:
            raise ValueError("Custom rule action or search scope is not supported")
        if indexer != "all" and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", indexer):
            raise ValueError("Custom rule indexer must be All indexers or a configured indexer id")
        if action in {"rewrite", "annotate"} and not value:
            raise ValueError("Rewrite and annotation rules need a replacement value")
        if not isinstance(enabled, bool) or not isinstance(locked, bool):
            raise ValueError("Custom rule enabled and locked fields must be booleans")
    elif action not in actions or scope not in scopes or not name or not match:
        return None
    return {
        "id": rule_id,
        "name": name,
        "match": match,
        "action": action,
        "scope": scope,
        "indexer": indexer,
        "value": value,
        "enabled": bool(enabled),
        "locked": bool(locked),
    }


def normalize_rules_config(payload: object, *, strict: bool = False) -> dict:
    if isinstance(payload, list):
        custom = []
        for old_rule in payload:
            if not isinstance(old_rule, dict):
                continue
            legacy_action = old_rule.get("action", "exclude")
            migrated = _normalize_custom_rule(
                {**old_rule, "action": "prefer" if legacy_action == "keep" else legacy_action, "scope": old_rule.get("scope", "all")},
                strict=False,
            )
            if migrated:
                custom.append(migrated)
        return {"schemaVersion": SCHEMA_VERSION, "defaults": default_rule_settings(), "customRules": custom}
    if not isinstance(payload, dict):
        if strict:
            raise ValueError("Request body must be an object")
        payload = {}

    if strict and payload.get("schemaVersion", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise ValueError("Reload the manager before saving this configuration")

    incoming_defaults = payload.get("defaults", {})
    if strict and not isinstance(incoming_defaults, dict):
        raise ValueError("defaults must be an object")
    defaults = default_rule_settings()
    if isinstance(incoming_defaults, dict):
        for rule_id, settings in incoming_defaults.items():
            if rule_id not in RULE_CATALOG:
                if strict:
                    raise ValueError(f"Unknown default rule: {rule_id}")
                continue
            if not isinstance(settings, dict):
                if strict:
                    raise ValueError(f"Settings for {rule_id} must be an object")
                continue
            for key in ("enabled", "locked"):
                if key in settings:
                    if not isinstance(settings[key], bool):
                        if strict:
                            raise ValueError(f"{rule_id}.{key} must be a boolean")
                        continue
                    defaults[rule_id][key] = settings[key]
            for key, limit in (("name", 64), ("description", 240)):
                if key in settings:
                    if not isinstance(settings[key], str):
                        if strict:
                            raise ValueError(f"{rule_id}.{key} must be a string")
                        continue
                    defaults[rule_id][key] = settings[key].strip()[:limit]
    # Older managers initialized every built-in rule as unlocked. Protect them
    # once on upgrade, then preserve deliberate unlocks from schema version 3.
    try:
        previous_version = int(payload.get("schemaVersion", 0))
    except (TypeError, ValueError):
        previous_version = 0
    if not strict and previous_version < 3:
        for settings in defaults.values():
            settings["locked"] = True
    custom = payload.get("customRules", [])
    if not isinstance(custom, list) or len(custom) > 200:
        if strict:
            raise ValueError("customRules must be a list with at most 200 rules")
        custom = []
    normalized_custom = []
    seen_ids = set()
    for rule in custom:
        if not isinstance(rule, dict):
            if strict:
                raise ValueError("customRules must contain rule objects")
            continue
        normalized = _normalize_custom_rule(rule, strict=strict)
        if normalized is None:
            continue
        if normalized["id"] in seen_ids:
            if strict:
                raise ValueError("Custom rule ids must be unique")
            continue
        seen_ids.add(normalized["id"])
        normalized_custom.append(normalized)
    return {"schemaVersion": SCHEMA_VERSION, "defaults": defaults, "customRules": normalized_custom}


def read_rules_config() -> dict:
    try:
        data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        return normalize_rules_config(data)
    except FileNotFoundError:
        return normalize_rules_config({})
    except (OSError, json.JSONDecodeError):
        return normalize_rules_config({})


def write_rules_config(config: dict) -> None:
    atomic_json(RULES_PATH, config)


def feed_rule_path(feed_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", feed_id):
        raise ValueError("Invalid feed id")
    return RULES_PATH.parent / "feed-rules" / f"{feed_id}.json"


def read_feed_rules(feed_id: str) -> dict:
    feed = next((value for value in INTEGRATIONS.feeds() if value["id"] == feed_id), None)
    if feed is None:
        raise ValueError("Feed not found")
    try:
        return normalize_rules_config(json.loads(feed_rule_path(feed_id).read_text(encoding="utf-8")))
    except FileNotFoundError:
        if feed["mode"] == "anime":
            config = copy.deepcopy(RULES_CONFIG)
        else:
            config = normalize_rules_config({})
            for rule_id in ("year-hygiene", "season-classification", "query-expansion", "dual-audio"):
                config["defaults"][rule_id]["enabled"] = False
        for settings in config["defaults"].values():
            settings["locked"] = True
        return config


def apply_connection_settings() -> None:
    connections = INTEGRATIONS.effective()["connections"]
    proxy.SONARR_URL = connections["sonarr"]["url"]
    proxy.SONARR_API_KEY = connections["sonarr"]["apiKey"]
    proxy._SONARR_SERIES_CACHE.clear()
    proxy._CACHE.clear()


def read_request_json(handler: object, maximum: int = 1_000_000) -> object:
    origin = handler.headers.get("Origin")
    if origin and urlparse(origin).netloc != handler.headers.get("Host"):
        raise ValueError("Cross-origin changes are not allowed")
    length = int(handler.headers.get("Content-Length", "0"))
    if length < 1 or length > maximum:
        raise ValueError("Invalid request body size")
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def validate_lock_transitions(current: dict, updated: dict) -> None:
    for rule_id, previous in current.get("defaults", {}).items():
        if not previous.get("locked"):
            continue
        candidate = updated["defaults"][rule_id]
        if any(candidate.get(key) != previous.get(key) for key in ("enabled", "name", "description")):
            raise ValueError(f"Unlock {rule_id} before changing its settings")

    updated_custom = {rule["id"]: rule for rule in updated.get("customRules", [])}
    for previous in current.get("customRules", []):
        if not previous.get("locked"):
            continue
        candidate = updated_custom.get(previous["id"])
        if candidate is None:
            raise ValueError(f"Unlock {previous['id']} before removing it")
        fields = ("enabled", "name", "match", "action", "scope", "indexer", "value")
        if any(candidate.get(key) != previous.get(key) for key in fields):
            raise ValueError(f"Unlock {previous['id']} before changing its settings")


RULES_CONFIG = read_rules_config()


def write_json(handler: object, status: HTTPStatus, data: object) -> None:
    payload = json.dumps(data).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(payload)


def has_valid_session(handler: object) -> bool:
    if not AUTH_ENABLED:
        return False
    cookie = SimpleCookie()
    try:
        cookie.load(handler.headers.get("Cookie", ""))
    except CookieError:
        return False
    morsel = cookie.get(SESSION_COOKIE)
    if morsel is None:
        return False
    try:
        expires, nonce, signature = morsel.value.split(".", 2)
        expires_at = int(expires)
    except (ValueError, TypeError):
        return False
    if expires_at <= int(time.time()) or not nonce:
        return False
    message = f"{AUTH_USERNAME}:{expires}:{nonce}".encode("utf-8")
    expected = hmac.new(SESSION_SIGNING_KEY, message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def session_cookie() -> str:
    expires = str(int(time.time()) + SESSION_TTL_SECONDS)
    nonce = secrets.token_urlsafe(24)
    message = f"{AUTH_USERNAME}:{expires}:{nonce}".encode("utf-8")
    signature = hmac.new(SESSION_SIGNING_KEY, message, hashlib.sha256).hexdigest()
    attributes = [f"{SESSION_COOKIE}={expires}.{nonce}.{signature}", "Path=/manager/", f"Max-Age={SESSION_TTL_SECONDS}", "HttpOnly", "SameSite=Strict"]
    if AUTH_COOKIE_SECURE:
        attributes.append("Secure")
    return "; ".join(attributes)


def clear_session_cookie() -> str:
    attributes = [f"{SESSION_COOKIE}=", "Path=/manager/", "Max-Age=0", "HttpOnly", "SameSite=Strict"]
    if AUTH_COOKIE_SECURE:
        attributes.append("Secure")
    return "; ".join(attributes)


def write_empty(handler: object, status: HTTPStatus, cookie: str | None = None) -> None:
    handler.send_response(status)
    handler.send_header("Content-Length", "0")
    handler.send_header("Cache-Control", "no-store")
    if cookie:
        handler.send_header("Set-Cookie", cookie)
    handler.end_headers()


def serve_file(handler: object, filename: str) -> None:
    asset = ROOT / filename
    payload = asset.read_bytes()
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", mimetypes.guess_type(asset.name)[0] or "application/octet-stream")
    handler.send_header("Content-Length", str(len(payload)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(payload)


def require_manager_auth(handler: object) -> bool:
    if not AUTH_ENABLED:
        write_json(handler, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Set AUTH_USERNAME and AUTH_PASSWORD to enable the manager."})
        return False
    if not has_valid_session(handler):
        write_json(handler, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required."})
        return False
    return True


def install_manager_routes() -> None:
    global INTEGRATIONS
    if INTEGRATIONS is None:
        INTEGRATIONS = IntegrationStore(Path(os.environ.get("INTEGRATIONS_PATH", str(RULES_PATH.parent / "integrations.json"))), LEGACY_SOURCES,
                                        {"sonarr": {"url": proxy.SONARR_URL, "apiKey": proxy.SONARR_API_KEY},
                                         "proxy": {"apiKey": proxy.PROXY_API_KEY}})
    proxy.configured_indexers = INTEGRATIONS.sources
    apply_connection_settings()
    connections = INTEGRATIONS.effective()["connections"]
    if os.environ.get("PROWLARR_DISCOVER_ON_START", "true" if os.environ.get("PROXY_FEEDS_JSON") else "false").lower() in {"true", "1", "yes"}:
        if connections["prowlarr"]["url"] and connections["prowlarr"]["apiKey"]:
            try:
                INTEGRATIONS.discover()
            except (ValueError, OSError):
                print("Prowlarr startup discovery failed; retry discovery in the manager.")
    for feed in INTEGRATIONS.feeds():
        target = feed_rule_path(feed["id"])
        if not target.exists():
            atomic_json(target, read_feed_rules(feed["id"]))
    install(proxy, lambda: RULES_CONFIG, feeds_provider=INTEGRATIONS.feeds,
            feed_rules_provider=read_feed_rules, legacy_sources_provider=LEGACY_SOURCES,
            feed_key_provider=lambda: INTEGRATIONS.effective()["connections"]["proxy"]["apiKey"])
    proxy_get = proxy.Handler.do_GET

    def do_get(self: object) -> None:
        path = urlparse(self.path).path
        if path in {"/manager/login", "/manager/login/"}:
            if has_valid_session(self):
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/manager/")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                serve_file(self, "login.html")
            return
        if path in STATIC_FILES:
            serve_file(self, STATIC_FILES[path])
            return
        icon_name = path.removeprefix("/manager/assets/icons/")
        if path.startswith("/manager/assets/icons/") and icon_name in ICON_FILES:
            serve_file(self, ICON_FILES[icon_name])
            return
        if path == "/manager":
            self.send_response(HTTPStatus.PERMANENT_REDIRECT)
            self.send_header("Location", "/manager/")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/manager/":
            if has_valid_session(self):
                serve_file(self, "index.html")
            else:
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/manager/login")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
            return
        if path == "/manager/app.js":
            if require_manager_auth(self):
                serve_file(self, "app.js")
            return
        if path == "/manager/api/rules":
            if not require_manager_auth(self):
                return
            try:
                feed_id = parse_qs(urlparse(self.path).query).get("feed", [""])[0]
                config = read_feed_rules(feed_id) if feed_id else RULES_CONFIG
                write_json(self, HTTPStatus.OK, config)
            except (OSError, ValueError) as error:
                write_json(self, HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        if path == "/manager/api/indexers":
            if not require_manager_auth(self):
                return
            write_json(self, HTTPStatus.OK, proxy.public_indexers())
            return
        if path in {"/manager/api/settings", "/manager/api/feeds", "/manager/api/sources"}:
            if not require_manager_auth(self):
                return
            getter = {"/manager/api/settings": INTEGRATIONS.public_settings,
                      "/manager/api/feeds": INTEGRATIONS.public_feeds,
                      "/manager/api/sources": INTEGRATIONS.public_sources}[path]
            write_json(self, HTTPStatus.OK, getter())
            return
        proxy_get(self)

    def do_put(self: object) -> None:
        global RULES_CONFIG
        path = urlparse(self.path).path
        if path not in {"/manager/api/rules", "/manager/api/settings", "/manager/api/feeds"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not require_manager_auth(self):
            return
        try:
            payload = read_request_json(self)
            if path == "/manager/api/settings":
                config = INTEGRATIONS.save_settings(payload)
                apply_connection_settings()
            elif path == "/manager/api/feeds":
                config = INTEGRATIONS.save_feeds(payload)
                for feed in INTEGRATIONS.feeds():
                    target = feed_rule_path(feed["id"])
                    if not target.exists():
                        atomic_json(target, read_feed_rules(feed["id"]))
            else:
                with RULES_LOCK:
                    feed_id = parse_qs(urlparse(self.path).query).get("feed", [""])[0]
                    config = normalize_rules_config(payload, strict=True)
                    validate_lock_transitions(read_feed_rules(feed_id) if feed_id else RULES_CONFIG, config)
                    if feed_id:
                        atomic_json(feed_rule_path(feed_id), config)
                    else:
                        write_rules_config(config)
                        RULES_CONFIG = config
        except (OSError, ValueError, UnicodeDecodeError) as error:
            write_json(self, HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        write_json(self, HTTPStatus.OK, config)

    def do_post(self: object) -> None:
        path = urlparse(self.path).path
        if path in {"/manager/api/discover", "/manager/api/test-connection", "/manager/api/sync-sonarr"}:
            if not require_manager_auth(self):
                return
            try:
                payload = read_request_json(self, 4096)
                if not isinstance(payload, dict):
                    raise ValueError("Request must be an object")
                if path == "/manager/api/discover":
                    result = INTEGRATIONS.discover()
                elif path == "/manager/api/sync-sonarr":
                    result = INTEGRATIONS.sync_sonarr()
                else:
                    result = INTEGRATIONS.test_connection(payload.get("service", ""))
                write_json(self, HTTPStatus.OK, result)
            except (OSError, ValueError, UnicodeDecodeError) as error:
                write_json(self, HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        if path == "/manager/api/login":
            if not AUTH_ENABLED:
                write_json(self, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Set AUTH_USERNAME and AUTH_PASSWORD to enable the manager."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 4096:
                    raise ValueError("Request body is too large")
                credentials = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(credentials, dict):
                    raise ValueError("Credentials must be an object")
                username = credentials.get("username", "")
                password = credentials.get("password", "")
                if not isinstance(username, str) or not isinstance(password, str):
                    raise ValueError("Credentials must be strings")
            except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
                write_json(self, HTTPStatus.BAD_REQUEST, {"error": "Invalid login request."})
                return
            valid_username = hmac.compare_digest(username.encode("utf-8"), AUTH_USERNAME.encode("utf-8"))
            valid_password = hmac.compare_digest(password.encode("utf-8"), AUTH_PASSWORD.encode("utf-8"))
            if not (valid_username and valid_password):
                write_json(self, HTTPStatus.UNAUTHORIZED, {"error": "Invalid username or password."})
                return
            write_empty(self, HTTPStatus.NO_CONTENT, session_cookie())
            return
        if path == "/manager/api/logout":
            write_empty(self, HTTPStatus.NO_CONTENT, clear_session_cookie())
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    proxy.Handler.do_GET = do_get
    proxy.Handler.do_PUT = do_put
    proxy.Handler.do_POST = do_post


if __name__ == "__main__":
    install_manager_routes()
    proxy.run()
