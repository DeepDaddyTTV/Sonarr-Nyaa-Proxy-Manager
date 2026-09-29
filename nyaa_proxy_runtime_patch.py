"""Runtime patch for the read-only Nyaa Season Proxy bind mount."""

from __future__ import annotations

from dataclasses import dataclass
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Dict, Iterable, List, Optional, Tuple


YEAR_TOKEN = re.compile(r"(?<!\d)[(\[]\s*(?:19|20)\d{2}\s*[)\]]")
SEASON_TOKEN = re.compile(
    r"(?ix)"
    r"\bS(?P<s_num>\d{1,2})(?:[ ._-]*E(?P<s_ep>\d{1,3}))?\b"
    r"|(?P<ordinal>\d{1,2})(?:st|nd|rd|th)\s+Season\b"
    r"|(?P<season_word>\bSeason)(?:[ ._-]*)(?P<w_num>\d{1,2})\b"
)
EPISODE_AFTER_SEASON = re.compile(
    r"(?ix)\s*[-:]\s*(?P<start>\d{1,3})"
    r"(?:\s*(?P<separator>[-~])\s*(?P<end>\d{1,3}))?"
)
FALLBACK_EPISODE = re.compile(
    r"(?ix)(?:^|\s)-\s*(?P<start>\d{1,3})"
    r"(?:\s*(?P<separator>[-~])\s*(?P<end>\d{1,3}))?(?=$|\s|[\[(])"
)
BATCH_MARKER = re.compile(r"(?ix)\b(?:batch|complete|collection)\b")
DUAL_AUDIO_MARKER = re.compile(r"(?ix)\bdual[\s._-]*audio\b")
TORZNAB_NS = "http://torznab.com/schemas/2015/feed"
ATOM_NS = "http://www.w3.org/2005/Atom"


@dataclass(frozen=True)
class ParsedRelease:
    season: Optional[int]
    episode_start: Optional[int]
    episode_end: Optional[int]
    kind: str
    marker_start: Optional[int] = None
    marker_end: Optional[int] = None
    episode_start_pos: Optional[int] = None
    episode_end_pos: Optional[int] = None
    cleaned_title: str = ""


def strip_year_tokens(title: str) -> str:
    return YEAR_TOKEN.sub("", title)


def _season_from_match(match: re.Match[str]) -> int:
    if match.group("s_num"):
        return int(match.group("s_num"))
    if match.group("ordinal"):
        return int(match.group("ordinal"))
    return int(match.group("w_num"))


def parse_release_title(title: str, requested_season: Optional[int] = None) -> ParsedRelease:
    """Classify a title without treating years, resolution, or bit depth as episodes."""
    cleaned = strip_year_tokens(title)
    marker = SEASON_TOKEN.search(cleaned)
    season: Optional[int] = None
    episode_start: Optional[int] = None
    episode_end: Optional[int] = None
    marker_start: Optional[int] = None
    marker_end: Optional[int] = None
    episode_start_pos: Optional[int] = None
    episode_end_pos: Optional[int] = None

    if marker:
        season = _season_from_match(marker)
        marker_start = marker.start()
        marker_end = marker.end()
        if marker.group("s_ep"):
            episode_start = int(marker.group("s_ep"))
            episode_start_pos = marker.start("s_ep")
            episode_end_pos = marker.end("s_ep")
        else:
            after = EPISODE_AFTER_SEASON.match(cleaned, marker.end())
            if after:
                episode_start = int(after.group("start"))
                episode_start_pos = after.start("start")
                episode_end_pos = after.end("start")
                if after.group("end"):
                    episode_end = int(after.group("end"))
                    episode_end_pos = after.end("end")
    else:
        fallback = FALLBACK_EPISODE.search(cleaned)
        if fallback:
            episode_start = int(fallback.group("start"))
            episode_start_pos = fallback.start("start")
            episode_end_pos = fallback.end("start")
            if fallback.group("end"):
                episode_end = int(fallback.group("end"))
                episode_end_pos = fallback.end("end")
            if requested_season is not None:
                season = requested_season

    if season is None:
        return ParsedRelease(None, episode_start, episode_end, "unknown", cleaned_title=cleaned)

    if episode_start is None:
        kind = "pack"
    elif episode_end is not None and (episode_end - episode_start + 1 >= 10 or BATCH_MARKER.search(cleaned)):
        kind = "pack"
    elif episode_end is not None:
        kind = "range"
    else:
        kind = "episode"

    return ParsedRelease(
        season=season,
        episode_start=episode_start,
        episode_end=episode_end,
        kind=kind,
        marker_start=marker_start,
        marker_end=marker_end,
        episode_start_pos=episode_start_pos,
        episode_end_pos=episode_end_pos,
        cleaned_title=cleaned,
    )


def _trim_marker_wrappers(text: str, start: int, end: int) -> Tuple[int, int]:
    if start > 0 and text[start - 1] in "([{" and end < len(text) and text[end] in ")]}":
        return start - 1, end + 1
    return start, end


def add_dual_audio_language_tokens(title: str) -> str:
    """Make Sonarr's title parser see both audio languages for dual-audio releases."""
    if not DUAL_AUDIO_MARKER.search(title):
        return title

    languages: List[str] = []
    if not re.search(r"(?i)\bjapanese\b", title):
        languages.append("Japanese")
    if not re.search(r"(?i)\benglish\b", title):
        languages.append("English")
    if not languages:
        return title
    return f"{title.rstrip()} [{' '.join(languages)}]"


def rewrite_title(title: str, parsed: ParsedRelease) -> str:
    """Rewrite a classified release to a Sonarr-safe Sxx or SxxExx title."""
    if parsed.kind == "unknown" or parsed.season is None:
        return add_dual_audio_language_tokens(title)

    text = parsed.cleaned_title
    if parsed.kind == "pack":
        replacement = f"S{parsed.season:02d}"
    elif parsed.kind == "episode" and parsed.episode_start is not None:
        replacement = f"S{parsed.season:02d}E{parsed.episode_start:02d}"
    else:
        return title

    if parsed.marker_start is not None and parsed.marker_end is not None:
        start, end = _trim_marker_wrappers(text, parsed.marker_start, parsed.marker_end)
        if parsed.episode_end_pos is not None and parsed.marker_end <= parsed.episode_end_pos:
            end = parsed.episode_end_pos
        elif parsed.episode_start_pos is not None and parsed.marker_end <= parsed.episode_start_pos:
            end = parsed.episode_start_pos
        text = text[:start] + replacement + text[end:]
    elif parsed.episode_start_pos is not None:
        prefix = re.sub(r"\s*-\s*$", " ", text[:parsed.episode_start_pos])
        text = prefix + replacement + text[parsed.episode_end_pos or parsed.episode_start_pos:]

    return add_dual_audio_language_tokens(re.sub(r"\s{2,}", " ", text).strip())


def add_torznab_language_attributes(feed_xml: bytes) -> bytes:
    """Annotate dual-audio items for Torznab clients that consume language attrs."""
    ET.register_namespace("atom", ATOM_NS)
    ET.register_namespace("torznab", TORZNAB_NS)
    root = ET.fromstring(feed_xml)
    for item in root.findall("./channel/item"):
        title = item.findtext("title") or ""
        if not DUAL_AUDIO_MARKER.search(title):
            continue
        existing = {
            (attribute.get("name"), attribute.get("value"))
            for attribute in item.findall(f"{{{TORZNAB_NS}}}attr")
        }
        # Sonarr maps Torznab language attributes by language *name*
        # (IsoLanguages.FindByName), so numeric ids would be ignored.
        for language_name in ("Japanese", "English"):
            if ("language", language_name) not in existing:
                ET.SubElement(
                    item,
                    f"{{{TORZNAB_NS}}}attr",
                    {"name": "language", "value": language_name},
                )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def search_variants(
    query: str,
    season: Optional[int],
    episode: Optional[int],
    series_year: Optional[int] = None,
) -> List[str]:
    """Build bounded, exact Nyaa query variants."""
    values: List[str] = []

    def add(value: str) -> None:
        value = re.sub(r"\s{2,}", " ", value).strip(" -_.")
        if value and value not in values:
            values.append(value)

    bases = [query]
    if series_year is not None:
        bases.insert(0, f"{query} {series_year}")

    if season is not None and episode is None:
        ordinal = ""
        if season >= 2:
            suffix = "th" if season % 100 in (11, 12, 13) else {1: "st", 2: "nd", 3: "rd"}.get(season % 10, "th")
            ordinal = f"{season}{suffix} Season"
        tokens = [f"Season {season}", f"Season {season:02d}", f"S{season:02d}", f"S{season}", ordinal, ""]
        for token in tokens:
            for base in bases:
                add(f"{base} {token}" if token else base)
    elif episode is not None:
        for base in bases:
            base = re.sub(r"(?ix)\b(?:S[ ._-]*0?\d{1,2}|Season[ ._-]*0?\d{1,2})\b", "", base)
            base = re.sub(r"\s{2,}", " ", base).strip(" -_.")
            for value in (f"{base} {episode:02d}", f"{base} E{episode:02d}", f"{base} S{season or 1:02d}E{episode:02d}"):
                add(value)
    else:
        add(query)
    return values[:12]


def install(module: object) -> None:
    """Install request-aware behavior over the original proxy module."""
    from dataclasses import replace

    module.REQUEST_TIMEOUT_SECONDS = min(module.REQUEST_TIMEOUT_SECONDS, 10)
    original_feed_xml = module.feed_xml
    original_query_bases = module.query_bases
    original_fetch_nyaa = module.fetch_nyaa
    original_first = module.first
    original_parse_season = module.parse_season
    original_fetch_sonarr_series = getattr(module, "fetch_sonarr_series", lambda: [])
    title_overrides: Dict[str, str] = {}

    def matches_series(release: object, query: str) -> bool:
        words = re.findall(r"[a-z0-9]+", query.lower())
        stop_words = {"a", "an", "and", "at", "for", "from", "in", "of", "on", "the", "to", "with"}
        anchors = [word for word in words if word not in stop_words and len(word) > 1]
        anchors = anchors[:3] if len(anchors) > 2 else anchors
        release_words = set(re.findall(r"[a-z0-9]+", release.normalized_title.lower()))
        return not anchors or all(word in release_words for word in anchors)

    def collect(
        queries: Iterable[str],
        season: Optional[str],
        episode: Optional[str],
        series_year: Optional[int],
    ) -> List[object]:
        requested_season = original_parse_season(season)
        requested_episode = int(episode) if episode and episode.isdigit() else None
        results: Dict[str, object] = {}
        for query in queries:
            for variant in search_variants(query, requested_season, requested_episode, series_year):
                try:
                    for release in original_fetch_nyaa(variant):
                        if not matches_series(release, query):
                            continue
                        parsed = parse_release_title(release.title, requested_season)
                        if requested_episode is not None:
                            if parsed.kind != "episode" or parsed.episode_start != requested_episode or parsed.season != requested_season:
                                continue
                        elif requested_season is not None:
                            if parsed.kind in ("episode", "range"):
                                continue
                            if parsed.season not in (None, requested_season):
                                continue
                        elif parsed.kind not in ("pack", "unknown"):
                            continue
                        results.setdefault(release.guid, release)
                        title_overrides[release.guid] = rewrite_title(release.title, parsed)
                except Exception as error:
                    print(f"fetch failed for query={variant!r}: {error}")
        return sorted(results.values(), key=lambda release: release.seeders, reverse=True)

    def patched_feed_xml(releases: Iterable[object], self_url: str) -> bytes:
        transformed = [
            replace(release, normalized_title=title_overrides.get(release.guid, release.normalized_title))
            for release in releases
        ]
        return add_torznab_language_attributes(original_feed_xml(transformed, self_url))

    module.Release.magnet_url = property(lambda self: "")
    module.Release.preferred_download_url = property(lambda self: self.download_url or "")
    module.feed_xml = patched_feed_xml

    def do_get(self: object) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed_url.query)
        if parsed_url.path in {"/", "/health"}:
            self.write_text("ok\n")
            return
        if parsed_url.path != "/api":
            self.send_error(404)
            return
        if not self.authorized(params):
            self.send_error(401)
            return
        action = original_first(params, "t", "search").lower()
        if action == "caps":
            self.write_xml(module.caps_xml())
            return
        season = original_first(params, "season", "")
        episode = original_first(params, "ep", "")
        series_year: Optional[int] = None
        tvdb_id = original_first(params, "tvdbid", "").strip()
        if tvdb_id:
            try:
                for series in original_fetch_sonarr_series():
                    if str(series.get("tvdbId") or "").strip() == tvdb_id:
                        series_year = int(series.get("year") or 0) or None
                        break
            except Exception as error:
                print(f"sonarr year lookup failed: {error}")
        print(
            "search t=%s q=%r tvdbid=%r imdbid=%r season=%r ep=%r"
            % (
                action,
                original_first(params, "q"),
                original_first(params, "tvdbid"),
                original_first(params, "imdbid"),
                season,
                episode,
            )
        )
        releases = collect(original_query_bases(params, season), season, episode, series_year)
        self.write_xml(module.feed_xml(releases, self.absolute_url()))

    module._proxy_parse_release_title = parse_release_title
    module._proxy_rewrite_title = rewrite_title
    module._proxy_add_dual_audio_language_tokens = add_dual_audio_language_tokens
    module._proxy_add_torznab_language_attributes = add_torznab_language_attributes
    module._proxy_search_variants = search_variants
    module.Handler.do_GET = do_get


def main() -> None:
    import nyaa_season_proxy as proxy
    install(proxy)
    proxy.run()


if __name__ == "__main__":
    main()
