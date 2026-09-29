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
        self.assertIn(b"Sonarr-Nyaa Proxy Manager", page)

        rules = [{"id": "one", "name": "Test rule", "type": "title-match", "match": "Judas", "action": "keep", "enabled": True}]
        status, _, _ = self.request("PUT", "/manager/api/rules", {"customRules": rules}, cookie=cookie)
        self.assertEqual(status, 200)
        status, _, body = self.request("GET", "/manager/api/rules", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["customRules"], rules)

        status, _, _ = self.request("GET", "/api?t=caps")
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
