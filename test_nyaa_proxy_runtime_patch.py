import unittest
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from types import SimpleNamespace

import nyaa_proxy_runtime_patch as proxy


FIXTURES = [
    (
        "[EMBER] The Duke of Death and His Maid (2021) (Season 1) [BDRip] [1080p Dual Audio HEVC 10 bits DD] (Shinigami Bocchan to Kuro Maid) (Batch)",
        1,
        "[EMBER] The Duke of Death and His Maid S01 [BDRip] [1080p Dual Audio HEVC 10 bits DD] (Shinigami Bocchan to Kuro Maid) (Batch) [Japanese English]",
        "pack",
    ),
    (
        "[EMBER] The Duke of Death and His Maid (2021) (Season 1) [1080p] [Dual Audio HEVC WEBRip] (Shinigami Bocchan to Kuro Maid) (Batch)",
        1,
        "[EMBER] The Duke of Death and His Maid S01 [1080p] [Dual Audio HEVC WEBRip] (Shinigami Bocchan to Kuro Maid) (Batch) [Japanese English]",
        "pack",
    ),
    (
        "[EMBER] The Duke of Death and His Maid (2023) (Season 2) [1080p] [Dual Audio HEVC WEBRip] (Shinigami Bocchan to Kuro Maid 2nd Season) (Batch)",
        2,
        "[EMBER] The Duke of Death and His Maid S02 [1080p] [Dual Audio HEVC WEBRip] (Shinigami Bocchan to Kuro Maid 2nd Season) (Batch) [Japanese English]",
        "pack",
    ),
    (
        "[EMBER] Shinigami Bocchan to Kuro Maid (2023) (Season 2) [1080p] [HEVC WEBRip] (The Duke of Death and His Maid Season 2) (Batch)",
        2,
        "[EMBER] Shinigami Bocchan to Kuro Maid S02 [1080p] [HEVC WEBRip] (The Duke of Death and His Maid Season 2) (Batch)",
        "pack",
    ),
    (
        "[EMBER] Shinigami Bocchan to Kuro Maid (2024) (Season 3) [1080p] [HEVC WEBRip] (The Duke of Death and His Maid Season 3) (Batch)",
        3,
        "[EMBER] Shinigami Bocchan to Kuro Maid S03 [1080p] [HEVC WEBRip] (The Duke of Death and His Maid Season 3) (Batch)",
        "pack",
    ),
    (
        "[Nobody] The Duke of Death and His Maid - Season 3 (Shinigami Bocchan to Kuro Maid) [DUAL AUDIO][CR WEB-DL][1080p]",
        3,
        "[Nobody] The Duke of Death and His Maid - S03 (Shinigami Bocchan to Kuro Maid) [DUAL AUDIO][CR WEB-DL][1080p] [Japanese English]",
        "pack",
    ),
    (
        "[DKB] Shinigami Bocchan to Kuro Maid - (Season 01) [1080p][HEVC x265 10bit][Multi-Subs][batch]",
        1,
        "[DKB] Shinigami Bocchan to Kuro Maid - S01 [1080p][HEVC x265 10bit][Multi-Subs][batch]",
        "pack",
    ),
    ("[SubsPlease] Shinigami Bocchan to Kuro Maid S01", 1, "[SubsPlease] Shinigami Bocchan to Kuro Maid S01", "pack"),
    (
        "[Erai-raws] Shinigami Bocchan to Kuro Maid 2nd Season - 01 ~ 12 [1080p][BATCH][Multiple Subtitle] [ENG][POR-BR][SPA-LA][SPA][ARA][FRE][GER][ITA][RUS]",
        2,
        "[Erai-raws] Shinigami Bocchan to Kuro Maid S02 [1080p][BATCH][Multiple Subtitle] [ENG][POR-BR][SPA-LA][SPA][ARA][FRE][GER][ITA][RUS]",
        "pack",
    ),
    (
        "[Erai-raws] Shinigami Bocchan to Kuro Maid 3rd Season - 01 [1080p][HEVC][Multiple Subtitle] [ENG][POR-BR][SPA-LA][SPA][ARA][FRE][GER][ITA][RUS]",
        3,
        "[Erai-raws] Shinigami Bocchan to Kuro Maid S03E01 [1080p][HEVC][Multiple Subtitle] [ENG][POR-BR][SPA-LA][SPA][ARA][FRE][GER][ITA][RUS]",
        "episode",
    ),
    (
        "[ASW] Shinigami Bocchan to Kuro Maid [1080p HEVC x265 10Bit][AAC] (Batch)",
        1,
        "[ASW] Shinigami Bocchan to Kuro Maid [1080p HEVC x265 10Bit][AAC] (Batch)",
        "unknown",
    ),
]


class ProxyFixtureTests(unittest.TestCase):
    def test_handoff_fixtures(self):
        for original, requested_season, expected, expected_kind in FIXTURES:
            with self.subTest(original=original):
                parsed = proxy.parse_release_title(original, requested_season)
                self.assertEqual(parsed.kind, expected_kind)
                self.assertEqual(proxy.rewrite_title(original, parsed), expected)

    def test_years_resolution_and_bit_depth_are_not_seasons(self):
        titles = [
            "[Group] Show (2021) [1080p HEVC 10 bits]",
            "[Group] Show 2023 1080p",
            "[Group] Show (2024) [2160p]",
        ]
        for title in titles:
            with self.subTest(title=title):
                parsed = proxy.parse_release_title(title, 1)
                self.assertIsNone(parsed.season)
                self.assertIsNone(parsed.episode_start)

    def test_episode_fallback_uses_requested_season(self):
        title = "[Anime Time] Welcome to Japan, Ms Elf! - 01 [1080p]"
        parsed = proxy.parse_release_title(title, 1)
        self.assertEqual(parsed.kind, "episode")
        self.assertEqual(proxy.rewrite_title(title, parsed), "[Anime Time] Welcome to Japan, Ms Elf! S01E01 [1080p]")

    def test_season_query_variants_include_unpadded_and_ordinal_forms(self):
        variants = proxy.search_variants("The Duke of Death and His Maid", 2, None)
        self.assertIn("The Duke of Death and His Maid Season 2", variants)
        self.assertIn("The Duke of Death and His Maid 2nd Season", variants)
        self.assertLessEqual(len(variants), 12)

    def test_dual_audio_titles_declare_japanese_and_english(self):
        title = "[EMBER] Show S01 [1080p Dual Audio HEVC] (Batch)"
        self.assertEqual(
            proxy.add_dual_audio_language_tokens(title),
            "[EMBER] Show S01 [1080p Dual Audio HEVC] (Batch) [Japanese English]",
        )
        self.assertEqual(
            proxy.add_dual_audio_language_tokens("Show S01 [Japanese English] [Dual Audio]"),
            "Show S01 [Japanese English] [Dual Audio]",
        )

    def test_dual_audio_feed_items_get_both_torznab_languages(self):
        feed = (
            b'<rss xmlns:torznab="http://torznab.com/schemas/2015/feed">'
            b'<channel><item><title>Show S01 [Dual Audio]</title>'
            b'<torznab:attr name="category" value="5070" /></item>'
            b'<item><title>Show S01 [English Dub]</title></item></channel></rss>'
        )
        root = ET.fromstring(proxy.add_torznab_language_attributes(feed))
        items = root.findall("./channel/item")
        attrs = items[0].findall("{http://torznab.com/schemas/2015/feed}attr")
        self.assertEqual(
            {(attr.get("name"), attr.get("value")) for attr in attrs},
            {("category", "5070"), ("language", "Japanese"), ("language", "English")},
        )
        self.assertEqual(items[1].findall("{http://torznab.com/schemas/2015/feed}attr"), [])

    def test_episode_ranges_are_not_misclassified_as_single_episodes(self):
        title = "[Judas] My Show S01E01-E12 [1080p]"
        parsed = proxy.parse_release_title(title, 1)
        self.assertEqual(parsed.kind, "pack")
        self.assertEqual(parsed.episode_start, 1)
        self.assertEqual(parsed.episode_end, 12)
        self.assertEqual(proxy.rewrite_title(title, parsed), "[Judas] My Show S01 [1080p]")


class RuntimeCollectionTests(unittest.TestCase):
    @staticmethod
    def make_module(releases, rules):
        @dataclass(frozen=True)
        class FakeRelease:
            title: str
            normalized_title: str
            guid: str
            seeders: int
            download_url: str = "https://nyaa.example/download.torrent"

            @property
            def magnet_url(self):
                return "magnet:?xt=urn:btih:fake"

            @property
            def preferred_download_url(self):
                return self.magnet_url or self.download_url

        class FakeHandler:
            def do_GET(self):
                pass

        def to_feed(items, _url):
            root = ET.Element("rss")
            channel = ET.SubElement(root, "channel")
            for release in items:
                item = ET.SubElement(channel, "item")
                ET.SubElement(item, "title").text = release.normalized_title
            return ET.tostring(root)

        return SimpleNamespace(
            REQUEST_TIMEOUT_SECONDS=20,
            Release=FakeRelease,
            Handler=FakeHandler,
            feed_xml=to_feed,
            query_bases=lambda _params, _season: ["My Show"],
            fetch_nyaa=lambda _query: releases,
            first=lambda _params, _key, default="": default,
            parse_season=lambda value: int(value) if value and str(value).isdigit() else None,
            fetch_sonarr_series=lambda: [],
            caps_xml=lambda: b"",
        )

    @staticmethod
    def release(title, seeders):
        return RuntimeCollectionTests.make_module([], SimpleNamespace).Release(
            title=title,
            normalized_title=title,
            guid=title,
            seeders=seeders,
        )

    def test_episode_and_season_scans_stay_separate(self):
        releases = [
            self.release("[Judas] My Show S01", 100),
            self.release("[Judas] My Show S01E02", 80),
            self.release("[Judas] My Show S01E01-E12 [Batch]", 70),
            self.release("[Judas] My Show S02E02", 60),
        ]
        rules = {"defaults": {"query-expansion": {"enabled": False}}, "customRules": []}
        module = self.make_module(releases, rules)
        proxy.install(module, lambda: rules)

        episode_results = module._proxy_collect(["My Show"], "1", "2", None)
        self.assertEqual([item.title for item in episode_results], ["[Judas] My Show S01E02"])

        season_results = module._proxy_collect(["My Show"], "1", None, None)
        self.assertEqual(
            {item.title for item in season_results},
            {"[Judas] My Show S01", "[Judas] My Show S01E01-E12 [Batch]"},
        )
        self.assertTrue(all("S01E" not in item.normalized_title for item in season_results))

    def test_custom_exclude_and_annotation_rules_apply_to_feed_titles(self):
        releases = [
            self.release("[Judas] My Show S01E02", 30),
            self.release("[Noisy] My Show S01E02", 90),
        ]
        rules = {
            "defaults": {"query-expansion": {"enabled": False}},
            "customRules": [
                {"enabled": True, "scope": "all", "match": "[Noisy]", "action": "exclude"},
                {"enabled": True, "scope": "episodes", "match": "[Judas]", "action": "annotate", "value": "Preferred"},
            ],
        }
        module = self.make_module(releases, rules)
        proxy.install(module, lambda: rules)
        found = module._proxy_collect(["My Show"], "1", "2", None)
        self.assertEqual(len(found), 1)
        self.assertIn("[Preferred]", found[0].normalized_title)


if __name__ == "__main__":
    unittest.main()
