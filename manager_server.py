"""Run the Sonarr-compatible proxy and serve the rule manager UI."""

from __future__ import annotations

import json
import mimetypes
import os
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

import nyaa_season_proxy as proxy
from nyaa_proxy_runtime_patch import install


ROOT = Path(__file__).resolve().parent
RULES_PATH = Path(os.environ.get("RULES_PATH", "/data/custom-rules.json"))
STATIC_FILES = {"/manager/": "index.html", "/manager": "index.html", "/manager/styles.css": "styles.css", "/manager/app.js": "app.js"}


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
    handler.end_headers()
    handler.wfile.write(payload)


def install_manager_routes() -> None:
    install(proxy)
    proxy_get = proxy.Handler.do_GET

    def do_get(self: object) -> None:
        path = urlparse(self.path).path
        if path == "/manager/api/rules":
            write_json(self, HTTPStatus.OK, {"customRules": read_custom_rules()})
            return
        filename = STATIC_FILES.get(path)
        if filename:
            asset = ROOT / filename
            payload = asset.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mimetypes.guess_type(asset.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        proxy_get(self)

    def do_put(self: object) -> None:
        if urlparse(self.path).path != "/manager/api/rules":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            rules = payload.get("customRules")
            if not isinstance(rules, list) or any(not isinstance(rule, dict) for rule in rules):
                raise ValueError("customRules must be a list of rule objects")
            write_custom_rules(rules)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            write_json(self, HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        write_json(self, HTTPStatus.OK, {"customRules": rules})

    proxy.Handler.do_GET = do_get
    proxy.Handler.do_PUT = do_put


if __name__ == "__main__":
    install_manager_routes()
    proxy.run()
