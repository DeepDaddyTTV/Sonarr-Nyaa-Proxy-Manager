"""Exercise manager authentication without contacting Nyaa or Sonarr."""

from __future__ import annotations

import http.client
import json
import copy
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

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
        self.assertTrue(all(rule["enabled"] and rule["locked"] for rule in defaults.values()))

        rules = [{
            "id": "one", "name": "Prefer Judas", "match": "Judas", "action": "prefer",
            "scope": "all", "indexer": "all", "value": "", "enabled": True, "locked": False,
        }]
        config = {"schemaVersion": 4, "defaults": defaults, "customRules": rules}
        config["defaults"]["dual-audio"]["locked"] = True
        status, _, _ = self.request("PUT", "/manager/api/rules", config, cookie=cookie)
        self.assertEqual(status, 200)
        status, _, body = self.request("GET", "/manager/api/rules", cookie=cookie)
        self.assertEqual(status, 200)
        saved = json.loads(body)
        self.assertEqual(saved["customRules"], rules)
        self.assertTrue(saved["defaults"]["dual-audio"]["locked"])
        self.assertEqual(json.loads(manager_server.RULES_PATH.read_text())["schemaVersion"], 4)

        locked_config = json.loads(body)
        locked_config["defaults"]["dual-audio"]["name"] = "Changed while locked"
        status, _, _ = self.request("PUT", "/manager/api/rules", locked_config, cookie=cookie)
        self.assertEqual(status, 400)
        unlocked_config = json.loads(body)
        unlocked_config["defaults"]["dual-audio"]["locked"] = False
        status, _, _ = self.request("PUT", "/manager/api/rules", unlocked_config, cookie=cookie)
        self.assertEqual(status, 200)
        unlocked_config["defaults"]["dual-audio"]["name"] = "Editable language rule"
        status, _, _ = self.request("PUT", "/manager/api/rules", unlocked_config, cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(manager_server.read_rules_config()["defaults"]["dual-audio"]["name"], "Editable language rule")
        self.assertFalse(manager_server.read_rules_config()["defaults"]["dual-audio"]["locked"])

        invalid = {"defaults": defaults, "customRules": [{**rules[0], "scope": "shell"}]}
        status, _, _ = self.request("PUT", "/manager/api/rules", invalid, cookie=cookie)
        self.assertEqual(status, 400)

        status, headers, icon_data = self.request("GET", "/manager/assets/icons/033-lock.png", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "image/png")
        self.assertTrue(icon_data.startswith(b"\x89PNG"))

        status, _, _ = self.request("GET", "/api?t=caps")
        self.assertEqual(status, 200)

    def test_legacy_custom_rules_migrate_with_locked_defaults(self) -> None:
        migrated = manager_server.normalize_rules_config([
            {"id": "legacy", "name": "Keep Judas", "match": "Judas", "action": "keep", "enabled": True}
        ])
        self.assertEqual(migrated["schemaVersion"], 4)
        self.assertEqual(migrated["customRules"][0]["action"], "prefer")
        self.assertEqual(migrated["customRules"][0]["indexer"], "all")
        self.assertTrue(all(rule["locked"] for rule in migrated["defaults"].values()))

    def test_upgrade_protects_defaults_and_preserves_saved_behavior(self) -> None:
        previous = {
            "schemaVersion": 2,
            "defaults": manager_server.default_rule_settings(),
            "customRules": [{"id": "custom", "name": "My preference", "match": "Group", "action": "prefer", "scope": "episodes", "enabled": False, "locked": False, "value": ""}],
        }
        for rule in previous["defaults"].values():
            rule["locked"] = False
        previous["defaults"]["year-hygiene"].update(enabled=False, name="My year rule", description="Custom description")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rules.json"
            path.write_text(json.dumps(previous))
            with patch.object(manager_server, "RULES_PATH", path):
                migrated = manager_server.read_rules_config()
                self.assertTrue(all(rule["locked"] for rule in migrated["defaults"].values()))
                self.assertFalse(migrated["defaults"]["year-hygiene"]["enabled"])
                self.assertEqual(migrated["defaults"]["year-hygiene"]["name"], "My year rule")
                self.assertEqual(migrated["defaults"]["year-hygiene"]["description"], "Custom description")
                self.assertEqual(migrated["customRules"], [{**previous["customRules"][0], "indexer": "all"}])
                migrated["defaults"]["year-hygiene"]["locked"] = False
                manager_server.write_rules_config(migrated)
                self.assertEqual(manager_server.read_rules_config(), migrated)

    def test_stale_manager_cannot_save_old_schema(self) -> None:
        with self.assertRaisesRegex(ValueError, "Reload the manager"):
            manager_server.normalize_rules_config({"schemaVersion": 3}, strict=True)

    def test_v3_upgrade_preserves_deliberately_unlocked_builtin_rules(self) -> None:
        previous = {"schemaVersion": 3, "defaults": manager_server.default_rule_settings(), "customRules": []}
        previous["defaults"]["dual-audio"]["locked"] = False
        migrated = manager_server.normalize_rules_config(previous)
        self.assertFalse(migrated["defaults"]["dual-audio"]["locked"])

    def test_indexer_list_is_authenticated_and_never_exposes_api_keys(self) -> None:
        status, _, _ = self.request("GET", "/manager/api/indexers")
        self.assertEqual(status, 401)
        cookie_status, headers, _ = self.request(
            "POST", "/manager/api/login", {"username": "test-user", "password": "test-password"}
        )
        self.assertEqual(cookie_status, 204)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        sources = [{
            "id": "private-indexer", "name": "Private Indexer", "type": "torznab",
            "url": "http://indexer:9696/api", "api_key": "do-not-leak", "categories": [],
        }]
        with patch.object(proxy, "configured_indexers", return_value=sources):
            status, _, body = self.request("GET", "/manager/api/indexers", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), [{"id": "private-indexer", "name": "Private Indexer"}])
        self.assertNotIn(b"do-not-leak", body)

    def test_rules_reject_malformed_indexer_ids(self) -> None:
        defaults = manager_server.default_rule_settings()
        rule = {
            "id": "bad-indexer", "name": "Bad", "match": "Group", "action": "exclude",
            "scope": "all", "indexer": "../private", "value": "", "enabled": True, "locked": False,
        }
        with self.assertRaisesRegex(ValueError, "indexer"):
            manager_server.normalize_rules_config(
                {"schemaVersion": 4, "defaults": defaults, "customRules": [rule]}, strict=True
            )

    def test_settings_and_profiles_require_auth_and_do_not_leak_keys(self) -> None:
        for endpoint in ("settings", "feeds", "sources"):
            self.assertEqual(self.request("GET", f"/manager/api/{endpoint}")[0], 401)
        _, headers, _ = self.request("POST", "/manager/api/login", {"username": "test-user", "password": "test-password"})
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        store = manager_server.INTEGRATIONS
        with patch.object(store, "data", copy.deepcopy(store.data)):
            status, _, body = self.request("PUT", "/manager/api/settings", {
                "connections": {"prowlarr": {"url": "http://prowlarr:9696", "apiKey": "secret-private-key"}}
            }, cookie=cookie)
            self.assertEqual(status, 200)
            self.assertNotIn(b"secret-private-key", body)
            status, _, body = self.request("GET", "/manager/api/settings", cookie=cookie)
            self.assertTrue(json.loads(body)["connections"]["prowlarr"]["hasApiKey"])
            self.assertNotIn(b"secret-private-key", body)
            status, _, body = self.request("PUT", "/manager/api/feeds", [
                {"id": "test-tv", "name": "Sonarr Proxy TV", "sourceIds": ["nyaa"], "mode": "tv"}
            ], cookie=cookie)
            self.assertEqual(status, 200)
            status, _, body = self.request("GET", "/manager/api/rules?feed=test-tv", cookie=cookie)
            self.assertEqual(status, 200)
            config = json.loads(body)
            self.assertFalse(config["defaults"]["dual-audio"]["enabled"])
            self.assertTrue(all(rule["locked"] for rule in config["defaults"].values()))
            config["customRules"] = [{"id": "only-tv", "name": "TV rule", "match": "TV", "scope": "all", "action": "exclude", "indexer": "all"}]
            self.assertEqual(self.request("PUT", "/manager/api/rules?feed=test-tv", config, cookie=cookie)[0], 200)
            self.assertFalse(any(rule["id"] == "only-tv" for rule in manager_server.RULES_CONFIG["customRules"]))
            self.assertEqual(self.request("GET", "/manager/api/rules?feed=unknown", cookie=cookie)[0], 400)


if __name__ == "__main__":
    unittest.main()
