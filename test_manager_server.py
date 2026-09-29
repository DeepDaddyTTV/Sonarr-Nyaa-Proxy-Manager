"""Exercise manager authentication without contacting Nyaa or Sonarr."""

from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

import manager_server
import nyaa_season_proxy as proxy


class ManagerAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data_dir = tempfile.TemporaryDirectory()
        manager_server.RULES_PATH = Path(cls.data_dir.name) / "rules.json"
        manager_server.RULES_CONFIG = manager_server.read_rules_config()
        manager_server.AUTH_USERNAME = "test-user"
        manager_server.AUTH_PASSWORD = "test-password"
        manager_server.AUTH_ENABLED = True
        manager_server.AUTH_COOKIE_SECURE = True
        manager_server.install_manager_routes()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), proxy.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.data_dir.cleanup()

    def request(self, method: str, path: str, payload: dict | None = None, cookie: str = "") -> tuple[int, dict, bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        body = json.dumps(payload) if payload is not None else None
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_login_and_rules_require_session(self) -> None:
        status, headers, _ = self.request("GET", "/manager/")
        self.assertEqual(status, 302)
        self.assertEqual(headers["Location"], "/manager/login")

        status, _, _ = self.request("GET", "/manager/api/rules")
        self.assertEqual(status, 401)

        status, _, _ = self.request("POST", "/manager/api/login", {"username": "test-user", "password": "wrong"})
        self.assertEqual(status, 401)

        status, headers, _ = self.request("POST", "/manager/api/login", {"username": "test-user", "password": "test-password"})
        self.assertEqual(status, 204)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("Secure", headers["Set-Cookie"])
        cookie = headers["Set-Cookie"].split(";", 1)[0]

        status, _, page = self.request("GET", "/manager/", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn(b"Sonarr Proxy Manager", page)

        status, _, body = self.request("GET", "/manager/api/rules", cookie=cookie)
        defaults = json.loads(body)["defaults"]
        self.assertEqual(len(defaults), 8)
        self.assertTrue(all(rule["enabled"] and not rule["locked"] for rule in defaults.values()))

        rules = [{
            "id": "one", "name": "Prefer Judas", "match": "Judas", "action": "prefer",
            "scope": "all", "value": "", "enabled": True, "locked": False,
        }]
        config = {"defaults": defaults, "customRules": rules}
        config["defaults"]["dual-audio"]["locked"] = True
        status, _, _ = self.request("PUT", "/manager/api/rules", config, cookie=cookie)
        self.assertEqual(status, 200)
        status, _, body = self.request("GET", "/manager/api/rules", cookie=cookie)
        self.assertEqual(status, 200)
        saved = json.loads(body)
        self.assertEqual(saved["customRules"], rules)
        self.assertTrue(saved["defaults"]["dual-audio"]["locked"])
        self.assertEqual(json.loads(manager_server.RULES_PATH.read_text())["schemaVersion"], 2)

        locked_config = json.loads(body)
        locked_config["defaults"]["dual-audio"]["name"] = "Changed while locked"
        status, _, _ = self.request("PUT", "/manager/api/rules", locked_config, cookie=cookie)
        self.assertEqual(status, 400)
        unlocked_config = json.loads(body)
        unlocked_config["defaults"]["dual-audio"]["locked"] = False
        status, _, _ = self.request("PUT", "/manager/api/rules", unlocked_config, cookie=cookie)
        self.assertEqual(status, 200)

        invalid = {"defaults": defaults, "customRules": [{**rules[0], "scope": "shell"}]}
        status, _, _ = self.request("PUT", "/manager/api/rules", invalid, cookie=cookie)
        self.assertEqual(status, 400)

        status, headers, icon_data = self.request("GET", "/manager/assets/icons/033-lock.png", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "image/png")
        self.assertTrue(icon_data.startswith(b"\x89PNG"))

        status, _, _ = self.request("GET", "/api?t=caps")
        self.assertEqual(status, 200)

    def test_legacy_custom_rules_migrate_to_version_two(self) -> None:
        migrated = manager_server.normalize_rules_config([
            {"id": "legacy", "name": "Keep Judas", "match": "Judas", "action": "keep", "enabled": True}
        ])
        self.assertEqual(migrated["schemaVersion"], 2)
        self.assertEqual(migrated["customRules"][0]["action"], "prefer")
        self.assertTrue(all(not rule["locked"] for rule in migrated["defaults"].values()))


if __name__ == "__main__":
    unittest.main()
