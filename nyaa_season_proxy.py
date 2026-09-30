#!/usr/bin/env python3
"""
Sonarr Proxy Manager

Small Torznab-compatible proxy that rewrites Nyaa anime batch titles before
Sonarr parses them. The main target is releases like:

  [Judas] Jujutsu Kaisen (Season 03) ... (Batch)

Sonarr often parses that as absolute episode 3. This proxy returns:

  [Judas] Jujutsu Kaisen S03 ... (Batch)

It also broadens searches so an S03 query can find Season 03 listings.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Iterable, List, Optional, Tuple


CONFIG_PATH = os.environ.get("SONARR_CONFIG_PATH", "/app/sonarr_proxy_config.json")


def load_local_config() -> dict:
    if not CONFIG_PATH:
        return {}

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as error:
        print(f"failed to load local config {CONFIG_PATH!r}: {error}", file=sys.stderr)
        return {}


LOCAL_CONFIG = load_local_config()

NYAA_BASE_URL = os.environ.get("NYAA_BASE_URL", LOCAL_CONFIG.get("nyaa_base_url", "https://nyaa.si")).rstrip("/")
NYAA_CATEGORY = os.environ.get("NYAA_CATEGORY", LOCAL_CONFIG.get("nyaa_category", "1_2"))
NYAA_FILTER = os.environ.get("NYAA_FILTER", LOCAL_CONFIG.get("nyaa_filter", "0"))
PROXY_API_KEY = os.environ.get("PROXY_API_KEY", LOCAL_CONFIG.get("proxy_api_key", ""))
SONARR_URL = os.environ.get("SONARR_URL", LOCAL_CONFIG.get("sonarr_url", "")).rstrip("/")
SONARR_API_KEY = os.environ.get("SONARR_API_KEY", LOCAL_CONFIG.get("sonarr_api_key", ""))
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "300"))
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "20"))
USER_AGENT = os.environ.get(
    "USER_AGENT",
    "sonarr-proxy-manager/1.0",
)
INDEXER_SOURCES = None
TRACKERS = [
    "udp://open.stealth.si:80/announce",
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://tracker.torrent.eu.org:451/announce",
]

TORZNAB_NS = "http://torznab.com/schemas/2015/feed"
NYAA_NS = "https://nyaa.si/xmlns/nyaa"

ET.register_namespace("torznab", TORZNAB_NS)
ET.register_namespace("atom", "http://www.w3.org/2005/Atom")

_CACHE: Dict[str, Tuple[float, List["Release"]]] = {}
_SONARR_SERIES_CACHE: Dict[str, Tuple[float, List[dict]]] = {}


@dataclass(frozen=True)
class Release:
    title: str
    normalized_title: str
    details_url: str
    download_url: str
    pub_date: str
    size_bytes: int
    seeders: int
    leechers: int
    downloads: int
    info_hash: str
    category_id: str
    category_name: str
    indexer_id: str = "nyaa"
    indexer_name: str = "Nyaa"
    source_guid: str = ""
    categories: Tuple[str, ...] = ()
    torznab_attributes: Tuple[Tuple[str, str], ...] = ()

    @property
    def guid(self) -> str:
        value = self.details_url or self.source_guid or self.download_url or self.info_hash or self.title
        return value if self.indexer_id == "nyaa" else f"{self.indexer_id}:{value}"

    @property
    def magnet_url(self) -> str:
        if not self.info_hash:
            return ""

        params = [("xt", f"urn:btih:{self.info_hash}"), ("dn", self.normalized_title)]
        params.extend(("tr", tracker) for tracker in TRACKERS)
        return "magnet:?" + urllib.parse.urlencode(params)

    @property
    def preferred_download_url(self) -> str:
        return self.magnet_url or self.download_url


def normalize_title(title: str) -> str:
    """Normalize anime season-pack wording into Sonarr-friendly Sxx tokens."""

    def season_repl(match: re.Match[str]) -> str:
        season = int(match.group("season"))
        return f"S{season:02d}"

    normalized = title

    # "(Season 03)", "[Season_03]", "{Season.03}" -> "S03"
    normalized = re.sub(
        r"(?ix)[\(\[\{]\s*season[\s._-]*(?P<season>\d{1,2})\s*[\)\]\}]",
        season_repl,
        normalized,
    )

    # Bare "Season 03" -> "S03". Avoid touching existing S03E01/S03 titles.
    normalized = re.sub(
        r"(?ix)(?<![A-Za-z0-9])season[\s._-]*(?P<season>\d{1,2})(?![A-Za-z0-9])",
        season_repl,
        normalized,
    )

    # "(S 03)" or "[S_03]" -> "S03".
    normalized = re.sub(
        r"(?ix)[\(\[\{]\s*S[\s._-]+(?P<season>\d{1,2})\s*[\)\]\}]",
        season_repl,
        normalized,
    )

    normalized = re.sub(r"\s{2,}", " ", normalized).strip()
    return normalized


def search_variants(q: str, season: Optional[str] = None) -> List[str]:
    """Return Nyaa query variants that cover both S03 and Season 03 naming."""

    variants: List[str] = []

    def add(value: str) -> None:
        cleaned = re.sub(r"\s{2,}", " ", value).strip()
        if cleaned and cleaned not in variants:
            variants.append(cleaned)

    add(q)

    # Prowlarr's indexer test/RSS probes can arrive without a search term.
    # Use a batch-specific fallback so validation works without returning weeklies.
    if not q.strip():
        add("batch")
        add("complete")

    season_number = parse_season(season)
    if season_number is not None and q:
        without_season = re.sub(
            r"(?ix)\b(?:S[\s._-]*0?\d{1,2}|Season[\s._-]*0?\d{1,2})\b",
            "",
            q,
        )
        without_season = re.sub(r"\s{2,}", " ", without_season).strip(" -_.")
        add(f"{without_season} S{season_number:02d}")
        add(f"{without_season} Season {season_number:02d}")
        add(f"{without_season} Season {season_number}")

        for prefix in shortened_title_prefixes(without_season):
            add(f"{prefix} S{season_number:02d}")
            add(f"{prefix} Season {season_number:02d}")

    for value in list(variants):
        for match in re.finditer(r"(?i)\bS[\s._-]*(\d{1,2})\b", value):
            number = int(match.group(1))
            token = match.group(0)
            add(value.replace(token, f"Season {number:02d}"))
            add(value.replace(token, f"Season {number}"))

        for match in re.finditer(r"(?i)\bSeason[\s._-]*(\d{1,2})\b", value):
            number = int(match.group(1))
            token = match.group(0)
            add(value.replace(token, f"S{number:02d}"))

    return variants[:12]


def shortened_title_prefixes(title: str) -> List[str]:
    """Try safe title prefixes for anime aliases that include arc subtitles."""

    cleaned = re.split(r"\s+[-:|]\s+", title, maxsplit=1)[0].strip()
    words = cleaned.split()
    prefixes: List[str] = []

    for length in (4, 3, 2):
        if len(words) > length:
            prefix = " ".join(words[:length])
            if prefix not in prefixes:
                prefixes.append(prefix)

    return prefixes


def fetch_sonarr_series() -> List[dict]:
    if not SONARR_URL or not SONARR_API_KEY:
        return []

    cache_key = f"{SONARR_URL}|series"
    cached = _SONARR_SERIES_CACHE.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    request = urllib.request.Request(
        f"{SONARR_URL}/api/v3/series",
        headers={
            "User-Agent": USER_AGENT,
            "X-Api-Key": SONARR_API_KEY,
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not isinstance(payload, list):
        return []

    _SONARR_SERIES_CACHE[cache_key] = (now, payload)
    return payload


def sonarr_titles_for_identifiers(params: Dict[str, List[str]], season: Optional[str]) -> List[str]:
    tvdb_id = first(params, "tvdbid", "").strip()
    imdb_id = first(params, "imdbid", "").strip().lower()
    season_number = parse_season(season)
    titles: List[str] = []

    def add(value: str) -> None:
        cleaned = re.sub(r"\s{2,}", " ", value).strip()
        if cleaned and cleaned not in titles:
            titles.append(cleaned)

    if not tvdb_id and not imdb_id:
        return titles

    try:
        series_list = fetch_sonarr_series()
    except Exception as error:
        print(f"sonarr lookup failed: {error}", file=sys.stderr)
        return titles

    for series in series_list:
        series_tvdb = str(series.get("tvdbId") or "").strip()
        series_imdb = str(series.get("imdbId") or "").strip().lower()
        if tvdb_id and series_tvdb != tvdb_id:
            continue
        if imdb_id and series_imdb != imdb_id:
            continue

        add(series.get("title", ""))
        for alt in series.get("alternateTitles", []) or []:
            alt_title = alt.get("title", "")
            scene_season = alt.get("sceneSeasonNumber")
            if season_number is not None and scene_season not in (None, -1, season_number):
                continue
            if season_number is None and scene_season not in (None, -1):
                continue
            add(alt_title)
        break

    return titles


def query_bases(params: Dict[str, List[str]], season: Optional[str]) -> List[str]:
    bases: List[str] = []

    def add(value: str) -> None:
        cleaned = re.sub(r"\s{2,}", " ", value).strip()
        if cleaned and cleaned not in bases:
            bases.append(cleaned)

    query = first(params, "q", "")
    add(query)

    if has_identifier(params):
        for title in sonarr_titles_for_identifiers(params, season):
            add(title)

    if not bases and not has_identifier(params):
        add("batch")
        add("complete")

    return bases


def is_season_pack_candidate(release: Release) -> bool:
    """Keep this proxy focused on batches/full-season packs, not weeklies."""

    title = release.normalized_title

    if re.search(r"(?i)\bS\d{1,2}E\d{1,3}\b", title):
        return False

    if re.search(r"(?i)(?:^|[\s._-])-\s*\d{1,3}\b", title):
        return False

    if re.search(r"(?i)\bE?\d{1,3}\s*[-~]\s*E?\d{1,3}\b", title):
        return True

    if re.search(r"(?i)\b(batch|complete|season[\s._-]?\d{1,2})\b", release.title):
        return True

    # Full-season releases often look like "Show S03 1080p ..." with no E token.
    if re.search(r"(?i)\bS\d{1,2}\b", title):
        return True

    return False


def parse_season(value: Optional[str]) -> Optional[int]:
    if not value:
        return None

    match = re.search(r"\d{1,2}", value)
    if not match:
        return None

    return int(match.group(0))


def parse_size(size_text: str) -> int:
    match = re.search(r"(?i)([\d.]+)\s*([KMGT]?i?B|B)", size_text.strip())
    if not match:
        return 0

    value = float(match.group(1))
    unit = match.group(2).lower()
    multipliers = {
        "b": 1,
        "kb": 1000,
        "kib": 1024,
        "mb": 1000**2,
        "mib": 1024**2,
        "gb": 1000**3,
        "gib": 1024**3,
        "tb": 1000**4,
        "tib": 1024**4,
    }
    return int(value * multipliers.get(unit, 1))


def configured_indexers() -> List[dict]:
    """Return Nyaa plus configured Torznab sources, without exposing secrets."""
    global INDEXER_SOURCES
    if INDEXER_SOURCES is not None:
        return INDEXER_SOURCES

    raw = os.environ.get("UPSTREAM_INDEXERS_JSON", LOCAL_CONFIG.get("upstream_indexers", "[]"))
    if isinstance(raw, str):
        try:
            extras = json.loads(raw)
        except json.JSONDecodeError as error:
            raise RuntimeError("UPSTREAM_INDEXERS_JSON must contain a JSON array") from error
    else:
        extras = raw
    if not isinstance(extras, list) or len(extras) > 19:
        raise RuntimeError("UPSTREAM_INDEXERS_JSON must be an array with at most 19 additional indexers")

    sources = [{
        "id": "nyaa",
        "name": "Nyaa",
        "type": "nyaa",
        "url": NYAA_BASE_URL,
        "category": NYAA_CATEGORY,
        "filter": NYAA_FILTER,
        "api_key": "",
        "categories": [],
    }]
    ids = {"nyaa"}
    for entry in extras:
        if not isinstance(entry, dict):
            raise RuntimeError("Each upstream indexer must be an object")
        indexer_id = str(entry.get("id") or "")
        name = str(entry.get("name") or "").strip()
        url = str(entry.get("url") or "").strip()
        parsed = urllib.parse.urlsplit(url)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", indexer_id) or indexer_id in ids:
            raise RuntimeError("Upstream indexer ids must be unique letters, numbers, underscores, or hyphens")
        if not name or len(name) > 64:
            raise RuntimeError(f"Upstream indexer {indexer_id!r} needs a name of 1 to 64 characters")
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise RuntimeError(f"Upstream indexer {indexer_id!r} needs an HTTP or HTTPS Torznab API URL")
        categories = entry.get("categories", [])
        if isinstance(categories, str):
            categories = [value.strip() for value in categories.split(",") if value.strip()]
        if not isinstance(categories, list) or any(not str(value).isdigit() for value in categories):
            raise RuntimeError(f"Upstream indexer {indexer_id!r} categories must be numeric Torznab IDs")
        sources.append({
            "id": indexer_id,
            "name": name,
            "type": "torznab",
            "url": url,
            "api_key": str(entry.get("api_key") or ""),
            "categories": [str(value) for value in categories],
        })
        ids.add(indexer_id)
    INDEXER_SOURCES = sources
    return sources


def public_indexers() -> List[dict]:
    return [{"id": source["id"], "name": source["name"]} for source in configured_indexers()]


def fetch_torznab(query: str, indexer_id: str, season: Optional[str] = None, episode: Optional[str] = None, *, params: Optional[dict] = None) -> List[Release]:
    source = next((item for item in configured_indexers() if item["id"] == indexer_id), None)
    if source is None or source["type"] != "torznab":
        return []

    extra = params or {}
    action = first(extra, "t", "tvsearch")
    if params is not None and action == "tvsearch" and not source.get("tvSearchParams", ["q"]):
        action = "search"
    categories = extra.get("cat", source["categories"])
    if params is not None and source.get("categories"):
        supported = set(str(value) for value in source["categories"])
        selected = set(str(value) for value in categories)
        narrowed = supported.intersection(selected)
        if narrowed:
            categories = sorted(narrowed)
        elif "5000" in supported:
            # Some trackers expose only parent TV, even when the virtual feed
            # correctly separates Sonarr's standard and anime search categories.
            categories = ["5000"]
        else:
            return []
    if params is not None and action == "search" and not extra.get("_absolute") and "5070" not in extra.get("cat", []):
        if extra.get("_date"):
            query = f"{query} {extra['_date']}"
        elif season and season.isdigit():
            token = f"S{int(season):02d}" + (f"E{int(episode):02d}" if episode and episode.isdigit() else "")
            if token.casefold() not in query.casefold():
                query = f"{query} {token}"
    cache_key = f"{source['url']}|{indexer_id}|{query}|{season or ''}|{episode or ''}|{json.dumps(extra, sort_keys=True)}"
    cached = _CACHE.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    parameters = [("t", action), ("q", query), ("limit", "100")]
    if action == "tvsearch":
        if season:
            parameters.append(("season", season))
        if episode and not extra.get("_absolute"):
            parameters.append(("ep", episode))
        for identifier in ("tvdbid", "imdbid"):
            if identifier in source.get("tvSearchParams", []) and first(extra, identifier):
                parameters.append((identifier, first(extra, identifier)))
    if categories:
        parameters.append(("cat", ",".join(str(value) for value in categories)))
    if source["api_key"]:
        parameters.append(("apikey", source["api_key"]))
    parts = urllib.parse.urlsplit(source["url"])
    replaced = {key for key, _value in parameters}
    existing_query = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if key not in replaced
    ]
    url = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(existing_query + parameters)))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        payload = response.read()

    root = ET.fromstring(payload)
    if root.tag == "error":
        raise ValueError("Upstream Torznab request failed")
    releases = [parse_torznab_item(item, source) for item in root.findall("./channel/item")]
    releases = [release for release in releases if release is not None]
    _CACHE[cache_key] = (now, releases)
    return releases


def parse_torznab_item(item: ET.Element, source: dict) -> Optional[Release]:
    def text(path: str) -> str:
        child = item.find(path)
        return child.text.strip() if child is not None and child.text else ""

    def attr(name: str) -> str:
        for child in item.findall(f"{{{TORZNAB_NS}}}attr"):
            if (child.get("name") or "").casefold() == name.casefold():
                return child.get("value", "")
        return ""

    title = text("title")
    if not title:
        return None
    enclosure = item.find("enclosure")
    link = text("link") or (enclosure.get("url", "") if enclosure is not None else "")
    magnet_url = attr("magneturl")
    if not link:
        link = magnet_url
    guid = text("guid")
    comments = text("comments")
    details_url = comments or (guid if guid.startswith(("http://", "https://")) else "")
    size = text("size") or attr("size") or (enclosure.get("length", "") if enclosure is not None else "")
    category = attr("category")
    category_name = attr("categoryname")
    seeders = parse_int(attr("seeders"))
    peers = parse_int(attr("peers"))
    return Release(
        title=title,
        normalized_title=normalize_title(title),
        details_url=details_url,
        download_url=link,
        pub_date=text("pubDate"),
        size_bytes=parse_size(size) if not size.isdigit() else int(size),
        seeders=seeders,
        leechers=max(0, peers - seeders),
        downloads=parse_int(attr("grabs")),
        info_hash=attr("infohash"),
        category_id=category or "5000",
        category_name=category_name or "TV",
        indexer_id=source["id"],
        indexer_name=source["name"],
        source_guid=guid,
        categories=tuple(child.get("value", "") for child in item.findall(f"{{{TORZNAB_NS}}}attr") if child.get("name") == "category"),
        torznab_attributes=tuple((child.get("name", ""), child.get("value", "")) for child in item.findall(f"{{{TORZNAB_NS}}}attr")),
    )


def nyaa_rss_url(query: str) -> str:
    params = {
        "page": "rss",
        "q": query,
        "c": NYAA_CATEGORY,
        "f": NYAA_FILTER,
    }
    return f"{NYAA_BASE_URL}/?{urllib.parse.urlencode(params)}"


def fetch_nyaa(query: str) -> List[Release]:
    cache_key = f"{NYAA_BASE_URL}|{NYAA_CATEGORY}|{NYAA_FILTER}|{query}"
    cached = _CACHE.get(cache_key)
    now = time.time()

    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    request = urllib.request.Request(nyaa_rss_url(query), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        payload = response.read()

    root = ET.fromstring(payload)
    releases = [parse_item(item) for item in root.findall("./channel/item")]
    releases = [release for release in releases if release is not None]
    _CACHE[cache_key] = (now, releases)
    return releases


def parse_item(item: ET.Element) -> Optional[Release]:
    def text(path: str, namespace: Optional[str] = None) -> str:
        if namespace:
            child = item.find(f"{{{namespace}}}{path}")
        else:
            child = item.find(path)
        return child.text.strip() if child is not None and child.text else ""

    title = text("title")
    if not title:
        return None

    details_url = text("guid")
    download_url = text("link")
    size_text = text("size", NYAA_NS)

    return Release(
        title=title,
        normalized_title=normalize_title(title),
        details_url=details_url,
        download_url=download_url,
        pub_date=text("pubDate"),
        size_bytes=parse_size(size_text),
        seeders=parse_int(text("seeders", NYAA_NS)),
        leechers=parse_int(text("leechers", NYAA_NS)),
        downloads=parse_int(text("downloads", NYAA_NS)),
        info_hash=text("infoHash", NYAA_NS),
        category_id=text("categoryId", NYAA_NS),
        category_name=text("category", NYAA_NS),
    )


def parse_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


def collect_releases(queries: Iterable[str], season: Optional[str]) -> List[Release]:
    by_guid: Dict[str, Release] = {}

    for query in queries:
        for variant in search_variants(query, season):
            try:
                for release in fetch_nyaa(variant):
                    if not is_season_pack_candidate(release):
                        continue
                    by_guid.setdefault(release.guid, release)
            except Exception as error:
                print(f"fetch failed for query={variant!r}: {error}", file=sys.stderr)

    return sorted(by_guid.values(), key=lambda release: release.seeders, reverse=True)


def caps_xml() -> bytes:
    caps = ET.Element("caps")
    ET.SubElement(caps, "server", title="Sonarr Proxy Manager", version="2.0")
    ET.SubElement(caps, "limits", max="100", default="100")

    searching = ET.SubElement(caps, "searching")
    ET.SubElement(searching, "search", available="yes", supportedParams="q")
    ET.SubElement(
        searching,
        "tv-search",
        available="yes",
        supportedParams="q,season,ep,tvdbid,imdbid",
    )

    categories = ET.SubElement(caps, "categories")
    tv = ET.SubElement(categories, "category", id="5000", name="TV")
    for category_id, name in (
        ("5020", "Foreign"),
        ("5030", "SD"),
        ("5040", "HD"),
        ("5045", "UHD"),
        ("5050", "Other"),
        ("5060", "Sport"),
        ("5070", "Anime"),
        ("5080", "Documentary"),
        ("5090", "Other"),
        ("5100", "WEB-DL"),
        ("5110", "WEBRip"),
        ("5120", "HDTV"),
    ):
        ET.SubElement(tv, "subcat", id=category_id, name=name)

    return xml_bytes(caps)


def feed_xml(releases: Iterable[Release], self_url: str) -> bytes:
    rss = ET.Element(
        "rss",
        {
            "version": "2.0",
        },
    )
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Sonarr Proxy Manager"
    ET.SubElement(channel, "description").text = "Filtered indexer results with Sonarr-friendly season and episode titles"
    ET.SubElement(channel, "link").text = self_url
    ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link", href=self_url, rel="self", type="application/rss+xml")

    for release in releases:
        item = ET.SubElement(channel, "item")
        download_url = release.preferred_download_url
        ET.SubElement(item, "title").text = release.normalized_title
        ET.SubElement(item, "guid", isPermaLink="true").text = release.guid
        ET.SubElement(item, "link").text = download_url
        ET.SubElement(item, "comments").text = release.details_url
        ET.SubElement(item, "pubDate").text = release.pub_date
        ET.SubElement(item, "size").text = str(release.size_bytes)
        ET.SubElement(
            item,
            "description",
        ).text = f"{release.normalized_title} | original: {release.title}"

        if download_url:
            ET.SubElement(
                item,
                "enclosure",
                url=download_url,
                length=str(release.size_bytes),
                type="application/x-bittorrent",
            )

        category_id = "5070" if release.indexer_id == "nyaa" else (release.category_id or "5000")
        add_torznab_attr(item, "category", category_id)
        add_torznab_attr(item, "seeders", str(release.seeders))
        add_torznab_attr(item, "peers", str(release.seeders + release.leechers))
        add_torznab_attr(item, "grabs", str(release.downloads))
        add_torznab_attr(item, "infohash", release.info_hash)
        add_torznab_attr(item, "magneturl", release.magnet_url)
        rewritten = {"category", "seeders", "peers", "grabs", "infohash", "magneturl"}
        for name, value in release.torznab_attributes:
            if name not in rewritten:
                add_torznab_attr(item, name, value)
        for additional in release.categories:
            if additional != category_id:
                add_torznab_attr(item, "category", additional)

    return xml_bytes(rss)


def add_torznab_attr(parent: ET.Element, name: str, value: str) -> None:
    if value:
        ET.SubElement(parent, f"{{{TORZNAB_NS}}}attr", name=name, value=value)


def xml_bytes(root: ET.Element) -> bytes:
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return payload


class Handler(BaseHTTPRequestHandler):
    server_version = "SonarrProxyManager/1.0"

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path in {"/", "/health"}:
            self.write_text("ok\n")
            return

        if parsed.path != "/api":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if not self.authorized(params):
            self.send_error(HTTPStatus.UNAUTHORIZED)
            return

        action = first(params, "t", "search").lower()
        if action == "caps":
            self.write_xml(caps_xml())
            return

        season = first(params, "season", "")
        releases = collect_releases(query_bases(params, season), season)
        self.write_xml(feed_xml(releases, self_url=self.absolute_url()))

    def authorized(self, params: Dict[str, List[str]]) -> bool:
        if not PROXY_API_KEY:
            return True

        supplied = first(params, "apikey", "") or self.headers.get("X-Api-Key", "")
        return supplied == PROXY_API_KEY

    def absolute_url(self) -> str:
        host = self.headers.get("Host", "localhost")
        return f"http://{host}{html.escape(self.path, quote=True)}"

    def write_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def write_xml(self, payload: bytes) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        message = re.sub(r"(?i)(apikey=)[^&\s\"]+", r"\1[redacted]", fmt % args)
        print(f"{self.address_string()} - {message}", file=sys.stderr)


def first(params: Dict[str, List[str]], name: str, default: str = "") -> str:
    values = params.get(name)
    return values[0] if values else default


def has_identifier(params: Dict[str, List[str]]) -> bool:
    return any(
        first(params, name, "").strip()
        for name in ("tvdbid", "imdbid", "rid", "tvmazeid", "traktid")
    )


def run() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8787"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Sonarr Proxy Manager listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
