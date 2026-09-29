import unittest
import xml.etree.ElementTree as ET

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


if __name__ == "__main__":
    unittest.main()
