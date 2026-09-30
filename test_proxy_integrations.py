"""Offline integration and request-isolation tests; no live Arr writes."""

import copy
import http.client
import importlib.util
import json
import io
import os
import sys
import tempfile
import threading
import unittest
import urllib.parse
import xml.etree.ElementTree as ET
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from proxy_integrations import IntegrationStore, TV_CATEGORIES, field_value, api_request
from nyaa_proxy_runtime_patch import install


LEGACY = [{"id": "nyaa", "name": "Nyaa", "type": "nyaa", "categories": []}]
FEEDS = [
    {"id": "anime", "name": "Sonarr Proxy Nyaa", "mode": "anime", "sourceIds": ["prowlarr-1"], "enabled": True, "tvCategories": TV_CATEGORIES},
    {"id": "tv", "name": "Sonarr Proxy Lime", "mode": "tv", "sourceIds": ["prowlarr-2"], "enabled": True, "tvCategories": TV_CATEGORIES},
]


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {key: "" for key in (
            "PROWLARR_URL", "PROWLARR_API_KEY", "SONARR_URL", "SONARR_API_KEY", "PROXY_PUBLIC_URL", "PROXY_API_KEY", "PROXY_FEEDS_JSON")})
        self.env.start()
        self.store = IntegrationStore(Path(self.folder.name) / "integrations.json", lambda: LEGACY)

    def tearDown(self):
        self.env.stop()
        self.folder.cleanup()

    def connect(self):
        return self.store.save_settings({"connections": {
            "prowlarr": {"url": "http://prowlarr:9696", "apiKey": "private-prowlarr-key"},
            "sonarr": {"url": "http://sonarr:8989", "apiKey": "private-sonarr-key"},
            "proxy": {"url": "http://proxy:8787", "apiKey": "private-proxy-key"},
        }})

    def discover(self):
        indexers = [
            {"id": 1, "name": "Nyaa", "protocol": "torrent", "enable": True, "capabilities": {"categories": [{"id": 5000, "subCategories": [{"id": 5070}]}]}, "fields": [{"name": "apiKey", "value": "must-not-store"}]},
            {"id": 2, "name": "LimeTorrents", "protocol": "torrent", "enable": True, "capabilities": {"categories": [{"id": 5040}]}},
            {"id": 3, "name": "Sonarr Proxy Anime", "protocol": "torrent"},
            {"id": 4, "name": "Another proxy name", "protocol": "torrent", "fields": [{"name": "baseUrl", "value": "http://proxy:8787"}, {"name": "apiPath", "value": "/feeds/anime/api"}]},
            {"id": 5, "name": "Usenet", "protocol": "usenet"},
            {"id": 6, "name": "Disabled", "protocol": "torrent", "enable": False},
            {"id": 7, "name": "Nyaa Season Proxy", "protocol": "torrent"},
        ]
        with patch("proxy_integrations.api_request", return_value=indexers):
            return self.store.discover()

    def test_credentials_redacted_persisted_private_and_blank_preserves(self):
        public = self.connect()
        self.assertNotIn("private-", json.dumps(public))
        self.assertTrue(public["connections"]["prowlarr"]["hasApiKey"])
        self.store.save_settings({"connections": {"prowlarr": {"apiKey": ""}}})
        self.assertEqual(self.store.effective()["connections"]["prowlarr"]["apiKey"], "private-prowlarr-key")
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)
        reloaded = IntegrationStore(self.store.path, lambda: LEGACY)
        self.assertEqual(reloaded.effective(), self.store.effective())

    def test_environment_precedence_and_read_only(self):
        with patch.dict(os.environ, {"PROWLARR_URL": "http://env-prowlarr:9696", "PROWLARR_API_KEY": "env-secret"}):
            self.assertTrue(self.store.public_settings()["connections"]["prowlarr"]["managed"]["apiKey"])
            with self.assertRaisesRegex(ValueError, "environment"):
                self.store.save_settings({"connections": {"prowlarr": {"apiKey": "different"}}})
            self.assertEqual(self.store.effective()["connections"]["prowlarr"]["apiKey"], "env-secret")
        self.assertNotIn("env-secret", self.store.path.read_text())

    def test_discovery_excludes_proxy_loops_disabled_and_usenet(self):
        self.connect()
        sources = self.discover()
        self.assertEqual([source["id"] for source in sources], ["nyaa", "prowlarr-1", "prowlarr-2"])
        self.assertEqual(sources[1]["categories"], [5000, 5070])
        self.assertNotIn("must-not-store", self.store.path.read_text())
        self.assertNotIn("private-", json.dumps(sources))
        self.assertEqual(self.store.sources()[1]["url"], "http://prowlarr:9696/1/api")

    def test_changed_prowlarr_connection_requires_rediscovery(self):
        self.connect()
        self.discover()
        self.store.save_settings({"connections": {"prowlarr": {"url": "http://new-prowlarr:9696"}}})
        self.assertEqual(len(self.store.sources()), 1)

    def test_invalid_feeds_and_parent_category_are_rejected(self):
        self.connect()
        self.discover()
        for invalid in (
            [{**FEEDS[0], "id": "../../outside"}], [{**FEEDS[0], "tvCategories": [5000]}],
            [{**FEEDS[0], "sourceIds": ["unknown"]}], [FEEDS[0], FEEDS[0]],
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.store.save_feeds(invalid)

    def test_compose_feeds_are_declarative(self):
        feeds = [{**FEEDS[0], "sourceIds": ["nyaa"]}]
        with patch.dict(os.environ, {"PROXY_FEEDS_JSON": json.dumps(feeds)}):
            self.assertEqual(self.store.feeds(), feeds)
            self.assertTrue(self.store.public_settings()["feedsManaged"])
            with self.assertRaisesRegex(ValueError, "PROXY_FEEDS_JSON"):
                self.store.save_feeds([])

    def test_sonarr_sync_is_idempotent_and_never_modifies_prowlarr(self):
        self.connect()
        self.discover()
        self.store.save_feeds(FEEDS)
        fields = ["baseUrl", "apiPath", "apiKey", "categories", "animeCategories", "animeStandardFormatSearch", "additionalParameters"]
        schema = {"implementation": "Torznab", "configContract": "TorznabSettings", "fields": [{"name": name, "value": ""} for name in fields]}
        original = {"id": 7, "name": "Nyaa (Prowlarr)", "implementation": "Torznab", "fields": [{"name": "baseUrl", "value": "http://prowlarr:9696/1"}]}
        entries = [copy.deepcopy(original)]
        writes = []

        def fake_api(_base, _key, path, method="GET", payload=None):
            if path == "/api/v3/indexer/schema":
                return [schema]
            if method == "GET":
                return copy.deepcopy(entries)
            entry = copy.deepcopy(payload)
            entry["id"] = entry.get("id", len(entries) + 10)
            entries[:] = [value for value in entries if value["id"] != entry["id"]] + [entry]
            writes.append((method, entry))
            return entry

        with patch("proxy_integrations.api_request", side_effect=fake_api):
            self.assertEqual([value["action"] for value in self.store.sync_sonarr()["entries"]], ["created", "created"])
            self.assertEqual([value["action"] for value in self.store.sync_sonarr()["entries"]], ["updated", "updated"])
            self.assertEqual(len(entries), 3)
            self.assertEqual(entries[0], original)
            anime, tv = entries[1:]
            self.assertEqual(field_value(anime, "categories"), [])
            self.assertEqual(field_value(anime, "animeCategories"), [5070])
            self.assertEqual(field_value(tv, "animeCategories"), [])
            self.assertNotIn(5000, field_value(tv, "categories"))
            self.assertFalse(anime["enableRss"])
            # Disabling affects only the manager's mapped entry, never deletes indexers.
            feeds = copy.deepcopy(FEEDS)
            feeds[0]["enabled"] = False
            self.store.save_feeds(feeds)
            self.store.sync_sonarr()
            self.assertFalse(entries[1]["enableInteractiveSearch"])
            entries[1]["fields"][0]["value"] = "http://different-app"
            with self.assertRaisesRegex(ValueError, "Ownership"):
                self.store.sync_sonarr()
        self.assertTrue(all(entry["id"] != 7 for _method, entry in writes))

    def test_api_errors_never_echo_secrets_or_response_bodies(self):
        import urllib.error
        error = urllib.error.HTTPError("http://host/?apikey=secret", 401, "secret response", {}, None)
        with patch("urllib.request.OpenerDirector.open", side_effect=error), self.assertRaises(ValueError) as caught:
            api_request("http://service", "secret", "/api/v1/indexer")
        self.assertNotIn("secret", str(caught.exception))


class FeedHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("isolated_proxy_for_tests", Path(__file__).with_name("nyaa_season_proxy.py"))
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)
        module = cls.module
        module.configured_indexers = lambda: [{"id": "prowlarr-1", "name": "Nyaa", "type": "torznab"}, {"id": "prowlarr-2", "name": "Lime", "type": "torznab"}]
        cls.calls = []
        module.fetch_sonarr_series = lambda: []
        cls.rules = {"anime": {"defaults": {"query-expansion": {"enabled": False}}, "customRules": []},
                     "tv": {"defaults": {key: {"enabled": False} for key in ("query-expansion", "season-classification", "dual-audio", "year-hygiene")}, "customRules": []}}

        def fetch(query, source, season=None, episode=None, params=None):
            cls.calls.append((source, query, copy.deepcopy(params)))
            titles = ["[Judas] My Show S01E02 [Dual Audio]", "[Judas] My Show S01 [Batch]", "[Judas] My Show - 02 [Dual Audio]", "[Judas] Wrong Series S01E02"] if source == "prowlarr-1" else ["My.Show.S01E02.Dual.Audio", "My.Show.S01.Complete", "My.Show.2026.09.30.1080p", "Wrong.Series.S01E02"]
            return [module.Release(title, title, f"https://tracker/{index}", f"http://prowlarr/download/{index}?apikey=upstream-secret", "", 10, 3, 1, 0, "", "5070" if source == "prowlarr-1" else "5040", "", indexer_id=source, indexer_name=source) for index, title in enumerate(titles)]

        module.fetch_torznab = fetch
        install(module, feeds_provider=lambda: FEEDS, feed_rules_provider=lambda feed_id: cls.rules[feed_id], feed_key_provider=lambda: "test-feed-key")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        sys.modules.pop("isolated_proxy_for_tests", None)

    def request(self, feed_id, query, key="test-feed-key"):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        client.request("GET", f"/feeds/{feed_id}/api?apikey={key}&{query}")
        response = client.getresponse()
        status, body = response.status, response.read()
        client.close()
        return status, body

    def titles(self, body):
        return [item.findtext("title") for item in ET.fromstring(body).findall("./channel/item")]

    def test_feed_authentication_and_scoped_capabilities(self):
        self.assertEqual(self.request("anime", "t=caps", key="wrong")[0], 401)
        self.assertEqual(self.request("unknown", "t=caps")[0], 404)
        for feed_id, expected in (("anime", {"5070"}), ("tv", set(map(str, TV_CATEGORIES)))):
            status, body = self.request(feed_id, "t=caps")
            self.assertEqual(status, 200)
            root = ET.fromstring(body)
            self.assertEqual({value.get("id") for value in root.findall("./categories/category/subcat")}, expected)

    def test_feed_accepts_api_key_header(self):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        client.request("GET", "/feeds/anime/api?t=caps", headers={"X-Api-Key": "test-feed-key"})
        response = client.getresponse()
        self.assertEqual(response.status, 200)
        response.read()
        client.close()

    def test_prowlarr_anime_retains_full_query_expansion(self):
        self.calls.clear()
        with patch.dict(self.rules["anime"]["defaults"], {"query-expansion": {"enabled": True}}):
            self.request("anime", "t=tvsearch&q=My+Show&season=1&cat=5070")
        self.assertGreater(len(self.calls), 3)

    def test_episode_searches_use_only_own_upstream_and_own_rules(self):
        self.calls.clear()
        status, anime = self.request("anime", "t=tvsearch&q=My+Show&season=1&ep=2&cat=5070")
        self.assertEqual(status, 200)
        self.assertEqual(len(self.titles(anime)), 2)
        self.assertTrue(all("Japanese English" in title for title in self.titles(anime)))
        self.assertTrue(all(call[0] == "prowlarr-1" for call in self.calls))
        self.calls.clear()
        status, tv = self.request("tv", "t=tvsearch&q=My+Show&season=1&ep=2&cat=5040")
        self.assertEqual(status, 200)
        self.assertEqual(self.titles(tv), ["My.Show.S01E02.Dual.Audio"])
        self.assertTrue(all(call[0] == "prowlarr-2" for call in self.calls))
        self.assertNotIn(b"Japanese", tv)

    def test_wrong_category_never_queries_upstream(self):
        self.calls.clear()
        status, body = self.request("anime", "t=tvsearch&q=My+Show&season=1&ep=2&cat=5040")
        self.assertEqual(status, 200)
        self.assertEqual(self.titles(body), [])
        self.assertEqual(self.calls, [])

    def test_season_results_exclude_single_episodes_and_preserve_feed_name(self):
        for feed_id in ("anime", "tv"):
            status, body = self.request(feed_id, "t=tvsearch&q=My+Show&season=1")
            self.assertEqual(status, 200)
            self.assertEqual(len(self.titles(body)), 1)
            self.assertNotIn("E02", self.titles(body)[0])
            self.assertEqual(ET.fromstring(body).findtext("./channel/title"), FEEDS[0 if feed_id == "anime" else 1]["name"])

    def test_absolute_anime_search_does_not_rewrite_absolute_number_as_season_episode(self):
        status, body = self.request("anime", "t=search&q=My+Show+02&cat=5070")
        self.assertEqual(status, 200)
        self.assertEqual(self.titles(body), ["[Judas] My Show - 02 [Dual Audio] [Japanese English]"])

    def test_daily_tv_search_preserves_date_and_language(self):
        status, body = self.request("tv", "t=tvsearch&q=My+Show&season=2026&ep=09%2F30")
        self.assertEqual(status, 200)
        self.assertEqual(self.titles(body), ["My.Show.2026.09.30.1080p"])

    def test_concurrent_profiles_do_not_leak_rule_context(self):
        responses = {}
        threads = [threading.Thread(target=lambda feed_id=feed_id: responses.update({feed_id: self.request(feed_id, "t=tvsearch&q=My+Show&season=1&ep=2")})) for feed_id in ("anime", "tv")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=6)
        self.assertIn(b"Japanese English", responses["anime"][1])
        self.assertNotIn(b"Japanese", responses["tv"][1])


class UpstreamRequestTests(unittest.TestCase):
    def test_generic_tracker_falls_back_to_search_and_parent_tv_category(self):
        import nyaa_season_proxy as proxy
        source = {"id": "lime-test", "name": "Lime", "type": "torznab", "url": "http://prowlarr/22/api",
                  "api_key": "test-key", "categories": [5000], "tvSearchParams": []}
        params = {"t": ["tvsearch"], "cat": ["5040"]}
        captured = []

        def respond(request, **_kwargs):
            captured.append(urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query))
            return io.BytesIO(b"<rss><channel /></rss>")

        with patch.object(proxy, "configured_indexers", return_value=[source]), patch("urllib.request.urlopen", side_effect=respond):
            proxy._CACHE.clear()
            proxy.fetch_torznab("Example Show", "lime-test", "1", "2", params=params)
            proxy.fetch_torznab("Example Show", "lime-test", "2026", "09/30", params={**params, "_date": "2026-09-30"})
        self.assertEqual(captured[0]["t"], ["search"])
        self.assertEqual(captured[0]["cat"], ["5000"])
        self.assertEqual(captured[0]["q"], ["Example Show S01E02"])
        self.assertNotIn("ep", captured[0])
        self.assertEqual(captured[1]["q"], ["Example Show 2026-09-30"])


if __name__ == "__main__":
    unittest.main()
