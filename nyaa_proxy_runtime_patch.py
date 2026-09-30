"""Runtime patch for the read-only Nyaa Season Proxy bind mount."""

from __future__ import annotations

from dataclasses import dataclass
from contextvars import ContextVar
import hmac
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Callable, Dict, Iterable, List, Optional, Tuple


YEAR_TOKEN = re.compile(r"(?<!\d)[(\[]\s*(?:19|20)\d{2}\s*[)\]]")
SEASON_TOKEN = re.compile(
    r"(?ix)"
    r"\bS(?P<s_num>\d{1,2})(?:[ ._-]*E(?P<s_ep>\d{1,3}))?\b"
    r"|\b(?P<x_num>\d{1,2})x(?P<x_ep>\d{1,3})\b"
    r"|(?P<ordinal>\d{1,2})(?:st|nd|rd|th)\s+Season\b"
    r"|(?P<season_word>\bSeason)(?:[ ._-]*)(?P<w_num>\d{1,2})\b"
)
EPISODE_AFTER_SEASON = re.compile(
    r"(?ix)(?:\s*[-:]\s*|[ ._-]+(?:Episode|Ep|E)[ ._-]*)(?P<start>\d{1,3})"
    r"(?:\s*(?P<separator>[-~])\s*(?P<end>\d{1,3}))?"
)
RANGE_END_AFTER_EPISODE = re.compile(r"(?ix)\s*[-~]\s*(?:\d{1,2}x)?E?(?P<end>\d{1,3})\b")
FALLBACK_EPISODE = re.compile(
    r"(?ix)(?:^|\s)-\s*(?P<start>\d{1,3})"
    r"(?:\s*(?P<separator>[-~])\s*(?P<end>\d{1,3}))?(?=$|\s|[\[(])"
)
BATCH_MARKER = re.compile(r"(?ix)\b(?:batch|complete|collection)\b")
EXPLICIT_EPISODE = re.compile(r"(?ix)\b(?:Episode|Ep|E)[ ._-]*(?P<start>\d{1,3})\b")
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
    if match.group("x_num"):
        return int(match.group("x_num"))
    if match.group("ordinal"):
        return int(match.group("ordinal"))
    return int(match.group("w_num"))


def parse_release_title(
    title: str,
    requested_season: Optional[int] = None,
    strip_year: bool = True,
) -> ParsedRelease:
    """Classify a title without treating years, resolution, or bit depth as episodes."""
    cleaned = strip_year_tokens(title) if strip_year else title
    date = re.search(r"(?<!\d)((?:19|20)\d{2})[._-](\d{2})[._-](\d{2})(?!\d)", cleaned)
    if date:
        return ParsedRelease(int(date.group(1)), None, None, "episode", cleaned_title=cleaned)
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
        episode_group = "s_ep" if marker.group("s_ep") else "x_ep"
        if marker.group(episode_group):
            episode_start = int(marker.group(episode_group))
            episode_start_pos = marker.start(episode_group)
            episode_end_pos = marker.end(episode_group)
            after_episode = RANGE_END_AFTER_EPISODE.match(cleaned, marker.end())
            if after_episode:
                episode_end = int(after_episode.group("end"))
                episode_end_pos = after_episode.end("end")
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
        fallback = FALLBACK_EPISODE.search(cleaned) or EXPLICIT_EPISODE.search(cleaned)
        if fallback:
            episode_start = int(fallback.group("start"))
            episode_start_pos = fallback.start("start")
            episode_end_pos = fallback.end("start")
            if fallback.groupdict().get("end"):
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


def rewrite_title(
    title: str,
    parsed: ParsedRelease,
    normalize: bool = True,
    dual_audio: bool = True,
) -> str:
    """Rewrite a classified release to a Sonarr-safe Sxx or SxxExx title."""
    if not normalize:
        return add_dual_audio_language_tokens(title) if dual_audio else title
    if parsed.kind == "unknown" or parsed.season is None:
        return add_dual_audio_language_tokens(title) if dual_audio else title

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

    normalized = re.sub(r"\s{2,}", " ", text).strip()
    return add_dual_audio_language_tokens(normalized) if dual_audio else normalized


def add_torznab_language_attributes(feed_xml: bytes, enabled: bool = True) -> bytes:
    """Annotate dual-audio items for Torznab clients that consume language attrs."""
    ET.register_namespace("atom", ATOM_NS)
    ET.register_namespace("torznab", TORZNAB_NS)
    root = ET.fromstring(feed_xml)
    for item in root.findall("./channel/item"):
        title = item.findtext("title") or ""
        if not enabled or not DUAL_AUDIO_MARKER.search(title):
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


def install(module: object, rules_provider: Optional[Callable[[], dict]] = None, *,
            feeds_provider=None, feed_rules_provider=None, legacy_sources_provider=None,
            feed_key_provider=None) -> None:
    """Install request-aware behavior over the original proxy module."""
    from dataclasses import replace

    module.REQUEST_TIMEOUT_SECONDS = min(module.REQUEST_TIMEOUT_SECONDS, 10)
    original_feed_xml = module.feed_xml
    original_query_bases = module.query_bases
    original_fetch_nyaa = module.fetch_nyaa
    original_fetch_torznab = getattr(module, "fetch_torznab", lambda *_args: [])
    indexers_provider = getattr(module, "configured_indexers", lambda: [{"id": "nyaa", "name": "Nyaa", "type": "nyaa"}])
    original_first = module.first
    original_parse_season = module.parse_season
    original_fetch_sonarr_series = getattr(module, "fetch_sonarr_series", lambda: [])
    original_magnet_url = module.Release.magnet_url
    original_preferred_download_url = module.Release.preferred_download_url
    active_feed = ContextVar("proxy_active_feed", default=None)
    request_parameters = ContextVar("proxy_request_parameters", default=None)

    def current_rules() -> dict:
        feed = active_feed.get()
        if feed is not None and feed_rules_provider is not None:
            return feed_rules_provider(feed["id"])
        try:
            return rules_provider() if rules_provider else {}
        except Exception:
            return {}

    def default_enabled(rule_id: str) -> bool:
        return current_rules().get("defaults", {}).get(rule_id, {}).get("enabled", True)

    def matches_series(release: object, query: str) -> bool:
        if not default_enabled("series-anchor"):
            return True
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
        config = current_rules()
        custom_rules = config.get("customRules", [])
        is_episode_search = requested_episode is not None
        is_season_search = requested_season is not None and requested_episode is None
        results: Dict[str, object] = {}
        preferred_releases: set[str] = set()
        feed = active_feed.get()
        sources = indexers_provider() if feed else (legacy_sources_provider or indexers_provider)()
        if feed:
            sources = [source for source in sources if source["id"] in feed["sourceIds"]]
        params = request_parameters.get()
        absolute_search = bool(params and params.get("_absolute"))
        daily_date = params.get("_date") if params else None
        if daily_date:
            is_episode_search, is_season_search = True, False
            requested_season = None
        for query in queries:
            variants = (
                search_variants(query, requested_season, requested_episode, series_year)
                if default_enabled("query-expansion")
                else [query]
            )
            for variant_index, variant in enumerate(variants):
                for source in sources:
                    if params and "5070" not in params.get("cat", []) and source.get("type") == "nyaa":
                        continue
                    # Anime aliases need the full expansion set, including through Prowlarr.
                    anime_request = bool(feed and params and "5070" in params.get("cat", []))
                    if source["id"] != "nyaa" and not anime_request and variant_index >= 3:
                        continue
                    try:
                        if source.get("type", "nyaa" if source["id"] == "nyaa" else "torznab") == "nyaa":
                            source_releases = original_fetch_nyaa(variant)
                        else:
                            args = (variant, source["id"], season, episode)
                            source_releases = original_fetch_torznab(*args, params=params) if params is not None else original_fetch_torznab(*args)
                        for release in source_releases:
                            if getattr(release, "indexer_id", source["id"]) != source["id"]:
                                release = replace(release, indexer_id=source["id"], indexer_name=source["name"])
                            if not matches_series(release, query):
                                continue
                            if feed:
                                categories = set(str(value) for value in getattr(release, "categories", ()) or (getattr(release, "category_id", ""),))
                                allowed = set(params.get("cat", [])) if params else set()
                                if allowed == {"5070"} and categories.intersection(str(value) for value in range(5001, 6000)) and "5070" not in categories:
                                    continue
                                if "5070" not in allowed and "5070" in categories:
                                    continue
                            parsed = parse_release_title(
                                release.title,
                                1 if absolute_search else requested_season,
                                strip_year=default_enabled("year-hygiene"),
                            )
                            if daily_date and default_enabled("episode-isolation"):
                                if not re.search(r"(?<!\d)" + re.escape(daily_date).replace(r"\-", "[._-]") + r"(?!\d)", release.title):
                                    continue
                            elif is_episode_search and default_enabled("episode-isolation"):
                                if parsed.kind != "episode" or parsed.episode_start != requested_episode or parsed.season != requested_season:
                                    if not (absolute_search and parsed.kind == "episode" and parsed.marker_start is None and parsed.episode_start == requested_episode):
                                        continue
                            elif is_season_search and default_enabled("season-isolation"):
                                if parsed.kind in ("episode", "range"):
                                    continue
                                if parsed.season not in (None, requested_season):
                                    continue
                            elif not is_episode_search and not is_season_search and parsed.kind not in ("pack", "unknown"):
                                continue

                            normalized_title = rewrite_title(
                                release.title,
                                parsed,
                                normalize=default_enabled("season-classification") and not absolute_search and not daily_date,
                                dual_audio=default_enabled("dual-audio"),
                            )
                            excluded = False
                            matched_preferences = False
                            for rule in custom_rules:
                                if not rule.get("enabled", True):
                                    continue
                                indexer = rule.get("indexer", "all")
                                if indexer not in ("all", release.indexer_id):
                                    continue
                                scope = rule.get("scope", "all")
                                if scope == "episodes" and not is_episode_search:
                                    continue
                                if scope == "seasons" and not is_season_search:
                                    continue
                                match = str(rule.get("match", ""))
                                if not match or match.casefold() not in release.title.casefold():
                                    continue
                                action = rule.get("action")
                                if action == "exclude":
                                    excluded = True
                                    break
                                if action == "prefer":
                                    matched_preferences = True
                                elif action == "rewrite":
                                    normalized_title = re.sub(
                                        re.escape(match),
                                        lambda _match: str(rule.get("value", "")),
                                        normalized_title,
                                        count=1,
                                        flags=re.IGNORECASE,
                                    )
                                elif action == "annotate":
                                    annotation = str(rule.get("value", "")).strip()
                                    if annotation:
                                        normalized_title = f"{normalized_title.rstrip()} [{annotation}]"
                            if excluded:
                                continue
                            results.setdefault(
                                release.guid,
                                replace(release, normalized_title=normalized_title),
                            )
                            if matched_preferences:
                                preferred_releases.add(release.guid)
                    except Exception as error:
                        print(f"fetch failed for indexer={source['id']!r}: {type(error).__name__}")
        return sorted(
            results.values(),
            key=lambda release: (release.guid in preferred_releases, release.seeders),
            reverse=True,
        )

    def patched_feed_xml(releases: Iterable[object], self_url: str) -> bytes:
        return add_torznab_language_attributes(
            original_feed_xml(releases, self_url),
            enabled=default_enabled("dual-audio"),
        )

    module.Release.magnet_url = property(
        lambda self: "" if default_enabled("direct-torrent") else original_magnet_url.fget(self)
    )
    module.Release.preferred_download_url = property(
        lambda self: (self.download_url or "")
        if default_enabled("direct-torrent")
        else original_preferred_download_url.fget(self)
    )
    module.feed_xml = patched_feed_xml

    def handle_search(self: object, parsed_url, params) -> None:
        action = original_first(params, "t", "search").lower()
        if action not in {"caps", "search", "tvsearch"}:
            self.send_error(400, "Unsupported Torznab action")
            return
        feed = active_feed.get()
        if action == "caps":
            payload = module.caps_xml()
            if feed:
                root = ET.fromstring(payload)
                root.find("server").set("title", feed["name"])
                allowed = set(str(value) for value in feed["tvCategories"] if feed["mode"] != "anime")
                if feed["mode"] != "tv":
                    allowed.add("5070")
                for parent in root.findall("./categories/category"):
                    for child in list(parent):
                        if child.get("id") not in allowed:
                            parent.remove(child)
                payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            self.write_xml(payload)
            return
        if feed and not feed["enabled"]:
            self.send_error(503, "Feed is disabled")
            return
        upstream = {key: list(value) for key, value in params.items() if key in {"t", "cat", "tvdbid", "imdbid", "offset", "limit", "q", "season", "ep"}}
        if feed:
            raw_categories = original_first(params, "cat", "")
            if raw_categories and not re.fullmatch(r"\d+(?:,\d+)*", raw_categories):
                self.send_error(400, "Invalid categories")
                return
            requested = set(raw_categories.split(",")) if raw_categories else set()
            allowed = set(str(value) for value in feed["tvCategories"] if feed["mode"] != "anime")
            if feed["mode"] != "tv":
                allowed.add("5070")
            selected = allowed if not requested or "5000" in requested else allowed.intersection(requested)
            if not selected:
                self.write_xml(module.feed_xml([], self.absolute_url()))
                return
            upstream["cat"] = sorted(selected)
        season = original_first(params, "season", "")
        episode = original_first(params, "ep", "")
        query = original_first(params, "q", "")
        if feed and feed["mode"] != "tv" and action == "search" and not season and not episode:
            absolute = re.search(r"\s+(\d{1,4})(?:v\d+)?$", query)
            if absolute and int(absolute.group(1)) < 1900:
                episode = absolute.group(1)
                query = query[:absolute.start()].strip()
                params = {**params, "q": [query]}
                upstream["_absolute"] = True
        if feed and re.fullmatch(r"\d{4}", season) and re.fullmatch(r"\d{2}/\d{2}", episode):
            upstream["_date"] = f"{season}-{episode.replace('/', '-')}"
        parameter_token = request_parameters.set(upstream if feed else None)
        try:
            perform_search(self, params, season, episode, feed)
        finally:
            request_parameters.reset(parameter_token)

    def perform_search(self: object, params, season, episode, feed) -> None:
        series_year: Optional[int] = None
        tvdb_id = original_first(params, "tvdbid", "").strip()
        identified_search = any(original_first(params, key, "").strip() for key in ("q", "tvdbid", "imdbid"))
        if feed and identified_search and (feed.get("animeTagId") or feed.get("tvTagId")):
            imdb_id = original_first(params, "imdbid", "").strip().casefold()
            query = original_first(params, "q", "").strip()
            normalize = lambda text: " ".join(re.findall(r"[a-z0-9]+", text.casefold()))
            candidates = []
            for series in original_fetch_sonarr_series():
                if tvdb_id or imdb_id:
                    if tvdb_id and str(series.get("tvdbId", "")) != tvdb_id:
                        continue
                    if imdb_id and str(series.get("imdbId", "")).casefold() != imdb_id:
                        continue
                else:
                    titles = [series.get("title", "")] + [value.get("title", "") for value in series.get("alternateTitles", [])]
                    if not query or normalize(query) not in {normalize(title) for title in titles}:
                        continue
                candidates.append(series)
            # Tag-based routing never changes series type or absolute numbering.
            def allowed_series(series):
                tags = series.get("tags", [])
                anime = feed.get("animeTagId") in tags
                tv = feed.get("tvTagId") in tags
                if feed["mode"] == "anime":
                    return anime
                if feed["mode"] == "tv":
                    return (tv if feed.get("tvTagId") else True) and not anime
                return anime or tv
            if not candidates or not all(allowed_series(series) for series in candidates):
                self.write_xml(module.feed_xml([], self.absolute_url()))
                return
        if tvdb_id:
            try:
                for series in original_fetch_sonarr_series():
                    if str(series.get("tvdbId") or "").strip() == tvdb_id:
                        series_year = int(series.get("year") or 0) or None
                        break
            except Exception:
                print("sonarr year lookup failed")
        queries = original_query_bases(params, season)
        releases = collect(queries, season, episode, series_year)
        payload = module.feed_xml(releases, self.absolute_url())
        if feed:
            root = ET.fromstring(payload)
            root.find("./channel/title").text = feed["name"]
            payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        self.write_xml(payload)

    def do_get(self: object) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed_url.query)
        if parsed_url.path in {"/", "/health"}:
            self.write_text("ok\n")
            return
        match = re.fullmatch(r"/feeds/([A-Za-z0-9_-]{1,64})/api", parsed_url.path)
        feed = None
        if match and feeds_provider:
            try:
                feed = next((value for value in feeds_provider() if value["id"] == match.group(1)), None)
            except (ValueError, OSError):
                self.send_error(503, "Feed configuration is unavailable")
                return
            if feed is None:
                self.send_error(404, "Feed not found")
                return
            key = feed_key_provider() if feed_key_provider else getattr(module, "PROXY_API_KEY", "")
            supplied_key = original_first(params, "apikey", "") or self.headers.get("X-Api-Key", "")
            if not key or not hmac.compare_digest(supplied_key.encode(), key.encode()):
                self.send_error(401)
                return
        elif parsed_url.path != "/api":
            self.send_error(404)
            return
        elif not self.authorized(params):
            self.send_error(401)
            return
        token = active_feed.set(feed)
        try:
            handle_search(self, parsed_url, params)
        except (ValueError, OSError):
            self.send_error(503, "Feed configuration is unavailable")
        finally:
            active_feed.reset(token)

    module._proxy_parse_release_title = parse_release_title
    module._proxy_rewrite_title = rewrite_title
    module._proxy_add_dual_audio_language_tokens = add_dual_audio_language_tokens
    module._proxy_add_torznab_language_attributes = add_torznab_language_attributes
    module._proxy_search_variants = search_variants
    module._proxy_collect = collect
    module._proxy_feed_context = active_feed
    module._proxy_request_context = request_parameters
    module.Handler.do_GET = do_get


def main() -> None:
    import nyaa_season_proxy as proxy
    install(proxy)
    proxy.run()


if __name__ == "__main__":
    main()
