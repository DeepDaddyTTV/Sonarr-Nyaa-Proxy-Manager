"""Run the Sonarr-compatible proxy and serve the rule manager UI."""

from __future__ import annotations

import json
import hashlib
import hmac
import mimetypes
import os
import secrets
import time
from http.cookies import CookieError, SimpleCookie
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

import nyaa_season_proxy as proxy
from nyaa_proxy_runtime_patch import install


ROOT = Path(__file__).resolve().parent
RULES_PATH = Path(os.environ.get("RULES_PATH", "/data/custom-rules.json"))
AUTH_USERNAME = os.environ.get("AUTH_USERNAME")
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD")
if (AUTH_USERNAME is None) != (AUTH_PASSWORD is None) or (
    AUTH_USERNAME is not None and (not AUTH_USERNAME or not AUTH_PASSWORD)
):
    raise RuntimeError("AUTH_USERNAME and AUTH_PASSWORD must be configured together")

AUTH_ENABLED = bool(AUTH_USERNAME and AUTH_PASSWORD)
AUTH_COOKIE_SECURE = os.environ.get("AUTH_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
SESSION_COOKIE = "NyaaProxyManagerSession"
SESSION_TTL_SECONDS = 12 * 60 * 60
SESSION_SIGNING_KEY = secrets.token_bytes(32)
STATIC_FILES = {
    "/manager/styles.css": "styles.css",
    "/manager/auth.js": "auth.js",
}


def read_custom_rules() -> list[dict]:
    try:
        data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError):
        return []


def write_custom_rules(rules: list[dict]) -> None:
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = RULES_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(rules, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(RULES_PATH)


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
    install(proxy)
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
            write_json(self, HTTPStatus.OK, {"customRules": read_custom_rules()})
            return
        proxy_get(self)

    def do_put(self: object) -> None:
        if urlparse(self.path).path != "/manager/api/rules":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not require_manager_auth(self):
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 1_000_000:
                raise ValueError("Request body is too large")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Request body must be an object")
            rules = payload.get("customRules")
            if not isinstance(rules, list) or any(not isinstance(rule, dict) for rule in rules):
                raise ValueError("customRules must be a list of rule objects")
            write_custom_rules(rules)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            write_json(self, HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        write_json(self, HTTPStatus.OK, {"customRules": rules})

    def do_post(self: object) -> None:
        path = urlparse(self.path).path
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
