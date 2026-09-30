"""MCP-to-manager integration tests using temporary data, never live Arr apps."""

import asyncio
import copy
import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
from contextlib import ExitStack
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import manager_server
import nyaa_season_proxy as proxy
from mcp_server import ManagerClient, ManagerError, create_server


@unittest.skipUnless(importlib.util.find_spec("mcp"), "Install requirements-mcp.txt to test MCP")
class MCPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = ExitStack()
        folder = cls.context.enter_context(tempfile.TemporaryDirectory())
        cls.context.enter_context(patch.dict(os.environ, {}, clear=True))
        for name, value in {
            "RULES_PATH": Path(folder) / "rules.json", "RULES_CONFIG": manager_server.normalize_rules_config({}),
            "INTEGRATIONS": None, "AUTH_USERNAME": "mcp-test-user", "AUTH_PASSWORD": "mcp-test-password",
            "AUTH_ENABLED": True, "AUTH_COOKIE_SECURE": False,
        }.items():
            cls.context.enter_context(patch.object(manager_server, name, value))
        cls.context.enter_context(patch.object(proxy, "configured_indexers", proxy.configured_indexers))
        for method in ("do_GET", "do_PUT", "do_POST"):
            if hasattr(proxy.Handler, method):
                cls.context.enter_context(patch.object(proxy.Handler, method, getattr(proxy.Handler, method)))
        cls.context.enter_context(patch.object(manager_server, "LEGACY_SOURCES", lambda: [
            {"id": "nyaa", "name": "Nyaa", "type": "nyaa", "categories": [5070]},
            {"id": "lime", "name": "LimeTorrents", "type": "torznab", "api_key": "hidden-source-key"},
        ]))
        manager_server.install_manager_routes()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), proxy.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.context.close()

    def setUp(self):
        manager_server.RULES_CONFIG = manager_server.normalize_rules_config({})
        manager_server.INTEGRATIONS.save_feeds([])
        manager_server.INTEGRATIONS.save_settings({"connections": {"prowlarr": {"url": "", "apiKey": None}}})
        self.client = ManagerClient(self.url, "mcp-test-user", "mcp-test-password", allow_writes=True)

    def call(self, name, arguments=None, *, client=None):
        from mcp import Client
        async def run():
            async with Client(create_server(client or self.client)) as session:
                return await session.call_tool(name, arguments or {})
        result = asyncio.run(run())
        self.assertFalse(result.is_error, result.content)
        return result.structured_content

    def rules(self, feed_id=""):
        return self.call("get_rules", {"feed_id": feed_id})

    def test_stdio_handshake_and_read_only_catalog(self):
        from mcp import Client, StdioServerParameters
        async def run():
            params = StdioServerParameters(command=sys.executable, args=[str(Path(__file__).with_name("mcp_server.py"))], env={
                "MCP_MANAGER_URL": self.url, "MCP_AUTH_USERNAME": "mcp-test-user", "MCP_AUTH_PASSWORD": "mcp-test-password",
            })
            async with Client(params, mode="legacy") as session:
                catalog = await session.list_tools()
                self.assertEqual({t.name for t in catalog.tools}, {"get_overview", "get_rules", "test_connection"})
                self.assertTrue(all(t.annotations.read_only_hint for t in catalog.tools))
                overview = await session.call_tool("get_overview")
                self.assertFalse(overview.is_error, overview.content)
                encoded = json.dumps(overview.structured_content)
                self.assertNotIn("mcp-test-password", encoded)
                self.assertNotIn("hidden-source-key", encoded)
                self.assertFalse(overview.structured_content["writesEnabled"])
        asyncio.run(run())

    def test_create_edit_lock_and_delete_custom_rule(self):
        revision = self.rules()["revision"]
        rule = {"rule_id": "prefer-ember", "name": "Prefer EMBER", "match": "[EMBER]", "action": "prefer",
                "expected_revision": revision, "scope": "episodes", "indexer": "nyaa"}
        saved = self.call("put_custom_rule", rule)
        self.assertEqual(saved["configuration"]["customRules"][0]["indexer"], "nyaa")
        locked = self.call("set_rule_lock", {"rule_id": "prefer-ember", "locked": True, "expected_revision": saved["revision"]})
        async def rejected():
            from mcp import Client
            async with Client(create_server(self.client)) as session:
                result = await session.call_tool("put_custom_rule", {**rule, "name": "Should not save", "expected_revision": locked["revision"]})
                self.assertTrue(result.is_error)
        asyncio.run(rejected())
        unlocked = self.call("set_rule_lock", {"rule_id": "prefer-ember", "locked": False, "expected_revision": locked["revision"]})
        edited = self.call("put_custom_rule", {**rule, "name": "Edited EMBER", "expected_revision": unlocked["revision"]})
        self.assertEqual(edited["configuration"]["customRules"][0]["name"], "Edited EMBER")
        deleted = self.call("delete_custom_rule", {"rule_id": "prefer-ember", "expected_revision": edited["revision"], "confirm": True})
        self.assertEqual(deleted["configuration"]["customRules"], [])

    def test_builtin_requires_separate_unlock(self):
        before = self.rules()
        async def rejected():
            from mcp import Client
            async with Client(create_server(self.client)) as session:
                result = await session.call_tool("update_builtin_rule", {"rule_id": "dual-audio", "enabled": False, "expected_revision": before["revision"]})
                self.assertTrue(result.is_error)
        asyncio.run(rejected())
        unlocked = self.call("set_rule_lock", {"rule_id": "dual-audio", "locked": False, "expected_revision": before["revision"]})
        saved = self.call("update_builtin_rule", {"rule_id": "dual-audio", "enabled": False, "expected_revision": unlocked["revision"]})
        self.assertFalse(saved["configuration"]["defaults"]["dual-audio"]["enabled"])
        self.assertTrue(saved["configuration"]["defaults"]["episode-isolation"]["enabled"])

    def test_server_rejects_stale_rules_and_feeds(self):
        config, revision = self.client.request("GET", "rules")
        changed = copy.deepcopy(config)
        changed["defaults"]["dual-audio"]["locked"] = False
        self.client.request("PUT", "rules", changed, revision)
        with self.assertRaisesRegex(ManagerError, "Configuration changed"):
            self.client.request("PUT", "rules", config, revision)
        feeds, revision = self.client.request("GET", "feeds")
        self.client.request("PUT", "feeds", [{"id": "anime", "name": "Anime", "mode": "anime", "sourceIds": ["nyaa"]}], revision)
        with self.assertRaisesRegex(ManagerError, "Configuration changed"):
            self.client.request("PUT", "feeds", feeds, revision)

    def test_feed_rules_are_isolated_and_no_sync_is_implicit(self):
        overview = self.call("get_overview")
        with patch.object(manager_server.INTEGRATIONS, "sync_sonarr") as sync:
            feed = self.call("put_feed", {"feed_id": "lime-tv", "name": "Sonarr Proxy Lime", "mode": "tv",
                                          "source_ids": ["lime"], "expected_revision": overview["feedsRevision"]})
            self.assertFalse(feed["sonarrSynced"])
            rules = self.rules("lime-tv")
            self.call("put_custom_rule", {"feed_id": "lime-tv", "rule_id": "no-cam", "name": "No CAM", "match": "CAM",
                                          "action": "exclude", "expected_revision": rules["revision"], "indexer": "lime"})
            self.assertEqual(self.rules()["configuration"]["customRules"], [])
            self.assertEqual(self.rules("lime-tv")["configuration"]["customRules"][0]["id"], "no-cam")
            sync.assert_not_called()

    def test_keys_loaded_from_environment_are_not_returned(self):
        with patch.dict(os.environ, {"MCP_PROWLARR_API_KEY": "private-test-api-value"}):
            settings = self.call("set_connection", {"service": "prowlarr", "url": "http://prowlarr:9696",
                                                     "load_api_key_from_environment": True})
        self.assertTrue(settings["connections"]["prowlarr"]["hasApiKey"])
        self.assertNotIn("private-test-api-value", json.dumps(settings))
        self.assertEqual(manager_server.INTEGRATIONS.effective()["connections"]["prowlarr"]["apiKey"], "private-test-api-value")

    def test_environment_settings_cannot_be_overwritten(self):
        with patch.dict(os.environ, {"PROWLARR_URL": "http://fixed-prowlarr:9696"}):
            with self.assertRaisesRegex(ManagerError, "environment-managed"):
                self.client.request("PUT", "settings", {"connections": {"prowlarr": {"url": "http://other:9696"}}})

    def test_confirmation_is_required_for_destructive_tools(self):
        from mcp import Client
        async def run():
            async with Client(create_server(self.client)) as session:
                for name, arguments in (
                    ("delete_custom_rule", {"rule_id": "nope", "expected_revision": "nope"}),
                    ("replace_rules", {"configuration": {}, "expected_revision": "nope"}),
                    ("sync_feeds_to_sonarr", {}),
                    ("set_connection", {"service": "prowlarr", "clear_api_key": True}),
                ):
                    result = await session.call_tool(name, arguments)
                    self.assertTrue(result.is_error)
        with patch.object(manager_server.INTEGRATIONS, "sync_sonarr") as sync:
            asyncio.run(run())
            sync.assert_not_called()

    def test_approved_import_and_explicit_sync(self):
        before = self.rules()
        config = before["configuration"]
        config["customRules"] = [{"id": "imported", "name": "Imported preference", "match": "Group", "action": "prefer",
                                  "scope": "all", "indexer": "all", "value": "", "enabled": True, "locked": False}]
        saved = self.call("replace_rules", {"configuration": config, "expected_revision": before["revision"], "confirm": True})
        self.assertEqual(saved["configuration"]["customRules"][0]["id"], "imported")
        with patch.object(manager_server.INTEGRATIONS, "sync_sonarr", return_value={"entries": [], "message": "Test only"}) as sync:
            result = self.call("sync_feeds_to_sonarr", {"confirm": True})
            self.assertEqual(result["entries"], [])
            sync.assert_called_once_with()

    def test_discovery_and_routing_are_explicit(self):
        with patch.object(manager_server.INTEGRATIONS, "discover", return_value=[]) as discover:
            self.assertEqual(self.call("discover_prowlarr_indexers"), {"sources": []})
            discover.assert_called_once_with()
        settings = self.call("set_routing_tags", {"anime_tag": "anime", "tv_tag": "tv"})
        self.assertEqual(settings["routing"], {"animeTag": "anime", "tvTag": "tv"})
        # Later tests read feed profiles without contacting Sonarr for routing tags.
        manager_server.INTEGRATIONS.save_settings({"connections": {}, "routing": {"animeTag": "", "tvTag": ""}})

    def test_auth_failure_and_read_only_helpers(self):
        readonly = ManagerClient(self.url, "mcp-test-user", "mcp-test-password")
        with self.assertRaisesRegex(ManagerError, "Writes are disabled"):
            readonly.request("PUT", "rules", {})
        invalid = ManagerClient(self.url, "mcp-test-user", "wrong-password")
        with self.assertRaisesRegex(ManagerError, "authentication failed"):
            invalid.request("GET", "settings")
        self.client.authenticated = True  # Expired session: retry login exactly once.
        self.assertIn("connections", self.client.request("GET", "settings")[0])

    def test_tool_catalog_has_no_code_or_deployment_access(self):
        from mcp import Client
        async def run():
            async with Client(create_server(self.client)) as session:
                tools = (await session.list_tools()).tools
                self.assertEqual(len(tools), 13)
                names = {t.name for t in tools}
                self.assertTrue({"put_custom_rule", "update_builtin_rule", "set_connection", "put_feed"}.issubset(names))
                self.assertFalse(any(word in name for name in names for word in ("shell", "file", "deploy", "exec", "radarr")))
                schemas = json.dumps([t.input_schema for t in tools])
                self.assertNotIn('"password"', schemas)
                self.assertNotIn('"apiKey"', schemas)
        asyncio.run(run())


class MCPURLTests(unittest.TestCase):
    def test_manager_origin_validation(self):
        for url in ("file:///etc/passwd", "http://user:password@host", "http://host/manager/", "http://host?key=secret"):
            with self.assertRaises(ManagerError):
                ManagerClient(url, "test", "test")
        with self.assertRaises(ManagerError):
            ManagerClient("http://127.0.0.1:8787", "", "")


if __name__ == "__main__":
    unittest.main()
