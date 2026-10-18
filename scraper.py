#!/usr/bin/env python3
"""
India IPTV scraper.

Sources
  * IPTVCat  (https://iptvcat.com/india)  - each channel is TWO table rows:
        row 1: flag | NAME (quality) [flags] | liveliness | status | checked | HD | Mbps
        row 2: "Add to list | copy | Download" -> list.iptvcat.com/my_list/s/<hash>.m3u8
    The Download link is a tiny M3U that contains the real stream URL, which we resolve.
  * iptv-org (https://iptv-org.github.io/iptv/countries/in.m3u) - maintained India playlist.
"""

import re
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://iptvcat.com"
INDIA_URL = "https://iptvcat.com/india"
INDIA_PAGE_FMT = "https://iptvcat.com/india__7/{n}"      # page 2,3,4... (seen in your log)
IPTVORG_URL = "https://iptv-org.github.io/iptv/countries/in.m3u"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://iptvcat.com/",
}

PROXY_SERVICES = []   # e.g. "http://proxy.example.com:8080"

LIST_LINK_RE = re.compile(r"list\.iptvcat\.com/my_list/", re.I)
QUALITY_RE = re.compile(r"\((\d{3,4})p\)")
FLAG_RE = re.compile(r"\[([^\]]*)\]")

BAD_NAMES = {"", "download", "play", "watch", "view", "open", "copy", "link", "add to list",
             "remove", "details", "more", "info", "online", "offline", "channel", "-", "+"}

CATEGORY_KEYWORDS = {
    "News": ["news", "ndtv", "aaj tak", "india today", "republic", "times now", "cnbc",
             "mirror now", "tv9", "news18", "wion", "dd news", "loksabha", "rajyasabha",
             "sansad", "khabar", "awaaz", "bharat express"],
    "Movies": ["star gold", "zee cinema", "sony max", "b4u movies", "movie", "movies",
               "cinema", "films", "flix", "zee bollywood", "pictures", "set max",
               "mastii", "romedy", "anmol cinema"],
    "Sports": ["star sports", "sony six", "sony ten", "dd sports", "eurosport", "sony esp",
               "sports", "cricket", "kabaddi"],
    "Kids": ["cartoon", "disney", "nick", "nickelodeon", "pogo", "hungama", "kids",
             "cbeebies", "baby tv"],
    "Music": ["mtv", "vh1", "9xm", "9x ", "zing", "music", "b4u music", "7s music",
              "balle balle", "jalwa", "jhakaas", "tashan"],
    "Devotional": ["aastha", "sanskar", "ishwar", "sadhna", "divya", "bhakti", "bhakthi",
                   "spiritual", "peace", "qtv", "bhajan", "om "],
    "Regional - Tamil": ["sun tv", "vijay", "kalaignar", "puthiya", "jaya", "captain",
                         "raj tv", "kolam", "tamil", "anandham", "polimer"],
    "Regional - Telugu": ["gemini", "maa tv", "ntv", "hmtv", "etv", "telugu", "star maa",
                          "abn", "sakshi", "bharat today"],
    "Regional - Malayalam": ["asianet", "surya", "mazhavil", "flowers", "safari", "reporter",
                             "media one", "kerala", "malayalam", "kairali", "manorama"],
    "Regional - Kannada": ["suvarna", "kannada", "udaya", "kasturi", "public tv", "tv5 kannada"],
    "Regional - Bengali": ["jalsha", "zee bangla", "sony aath", "bengali", "bangla",
                           "akd", "aakaash aath", "ananda", "calcutta", "kolkata"],
    "Regional - Marathi": ["pravah", "zee marathi", "colors marathi", "sony marathi", "saam",
                           "marathi", "mi marathi"],
    "Regional - Gujarati": ["dd girnar", "gujarati", "vtv", "zee 24 kalak", "tv9 gujarati"],
    "Regional - Punjabi": ["ptc", "punjabi", "mh1", "chardikla"],
    "Regional - Bhojpuri": ["bhojpuri"],
    "Infotainment": ["discovery", "nat geo", "national geographic", "history", "animal planet",
                     "tlc", "travel", "food", "living", "xplor"],
    "English": ["bbc", "cnn", "fox", "espn", "hbo", "star world", "zee cafe", "zee café",
                "english"],
    "Entertainment": ["star plus", "zee tv", "sony", "colors", "life ok", "sab", "star one",
                      "imagine", "bindass", "&tv", "&prive", "star utsav", "zee anmol",
                      "rishtey", "entertainment"],
}
_CAT_PATTERNS = [
    (cat, re.compile(r"(?<![a-z0-9])(?:%s)" % "|".join(re.escape(k.strip()) for k in kws), re.I))
    for cat, kws in CATEGORY_KEYWORDS.items()
]


def clean_name(text):
    return re.sub(r"\s+", " ", text or "").strip()


def is_bad_name(text):
    t = clean_name(text).lower()
    return t in BAD_NAMES or re.fullmatch(r"[\d\W_]+", t) is not None


def split_name(raw):
    """'7S Music (576p) [Not 24/7]' -> ('7S Music', 576, ['Not 24/7'])"""
    raw = clean_name(raw)
    q = QUALITY_RE.search(raw)
    quality = int(q.group(1)) if q else 0
    flags = [f.strip() for f in FLAG_RE.findall(raw)]
    base = clean_name(QUALITY_RE.sub("", FLAG_RE.sub("", raw)))
    return base, quality, flags


def categorize(name, fallback=None):
    for cat, pat in _CAT_PATTERNS:
        if pat.search(name):
            return cat
    return fallback or "General"


class IPTVCatScraper:
    def __init__(self, use_proxy=False, workers=6, debug_html=False):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.workers = workers
        self.debug_html = debug_html
        if use_proxy and PROXY_SERVICES:
            self.session.proxies = {"http": PROXY_SERVICES[0], "https": PROXY_SERVICES[0]}

    # ── HTTP (IPTVCat returns 502 often, so retry with back-off) ──────────
    def fetch_page(self, url, retries=5):
        for attempt in range(retries):
            try:
                r = self.session.get(url, timeout=30)
                r.raise_for_status()
                return r.text
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{retries} failed for {url}: {e}")
                time.sleep(min(2 ** attempt, 20))
        return None

    # ── Parsing the two-row layout ────────────────────────────────────────
    def parse_channels(self, html):
        soup = BeautifulSoup(html, "html.parser")
        channels, pending = [], None

        for row in soup.find_all("tr"):
            link = row.find("a", href=LIST_LINK_RE)
            if link:
                if pending:
                    base, quality, flags = split_name(pending)
                    if base and not is_bad_name(base):
                        channels.append({
                            "name": base, "quality": quality, "flags": flags,
                            "stream_url": urljoin(BASE_URL, link["href"]),
                            "is_online": True,
                            "category": categorize(base),
                            "logo": "", "source": "iptvcat",
                        })
                pending = None
                continue

            tds = row.find_all("td", recursive=False)
            if len(tds) >= 4:
                # name is the first cell that has real text (cell 0 only holds flag images)
                for td in tds[:3]:
                    txt = clean_name(td.get_text(" ", strip=True))
                    if txt and not is_bad_name(txt) and "add to list" not in txt.lower():
                        pending = txt
                        break
        return channels

    # ── Resolve IPTVCat "Download" link -> real stream URL ────────────────
    def resolve_list_link(self, url):
        for attempt in range(3):
            try:
                r = self.session.get(url, timeout=20)
                if r.status_code >= 500:
                    time.sleep(1 + attempt)
                    continue
                r.raise_for_status()
                # redirected straight to the stream?
                if r.history and not LIST_LINK_RE.search(r.url):
                    return r.url
                text = r.text
                if "#EXT-X-" in text:        # the link is itself an HLS playlist
                    return url
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith(("http://", "https://")) and not LIST_LINK_RE.search(line):
                        return line
                return None
            except Exception as e:
                logger.debug(f"resolve failed {url}: {e}")
                time.sleep(1)
        return None

    def _resolve_channel(self, ch):
        ch["stream_url"] = self.resolve_list_link(ch["stream_url"])
        time.sleep(0.2)
        return ch

    # ── Pagination ────────────────────────────────────────────────────────
    def scrape_iptvcat(self, max_pages=10, include_not_247=False):
        logger.info("Scraping IPTVCat India...")
        raw, seen_names = [], set()
        for n in range(1, max_pages + 1):
            url = INDIA_URL if n == 1 else INDIA_PAGE_FMT.format(n=n)
            html = self.fetch_page(url)
            if not html:
                logger.warning(f"Page {n} unavailable, stopping pagination")
                break
            if self.debug_html and n == 1:
                with open("logs/page1.html", "w", encoding="utf-8") as f:
                    f.write(html)
            found = self.parse_channels(html)
            new = [c for c in found if (c["name"], c["stream_url"]) not in seen_names]
            for c in new:
                seen_names.add((c["name"], c["stream_url"]))
            logger.info(f"  page {n}: {len(found)} channels ({len(new)} new)")
            if not new:
                break
            raw.extend(new)
            time.sleep(1)

        if not raw:
            logger.error("IPTVCat parse found 0 channels. Run with --debug-html and check logs/page1.html")
            return []

        if not include_not_247:
            raw = [c for c in raw if not any("not 24/7" in f.lower() for f in c["flags"])]

        logger.info(f"Resolving real stream URLs for {len(raw)} IPTVCat channels...")
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            resolved = list(ex.map(self._resolve_channel, raw))
        out = [c for c in resolved if c["stream_url"] and not LIST_LINK_RE.search(c["stream_url"])]
        logger.info(f"IPTVCat: {len(out)} channels with a real stream URL")
        return out

    # ── iptv-org source ───────────────────────────────────────────────────
    def scrape_iptvorg(self):
        logger.info("Fetching iptv-org India playlist...")
        text = self.fetch_page(IPTVORG_URL, retries=3)
        if not text:
            return []
        out, meta, skip = [], None, False
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("#EXTINF"):
                attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', line))
                raw_name = line.split(",", 1)[-1]
                meta = (raw_name, attrs)
                skip = False
            elif line.startswith("#EXTVLCOPT") or line.startswith("#EXTHTTP"):
                if re.search(r"referrer|user-agent|header", line, re.I):
                    skip = True            # needs custom headers a TV player can't send
            elif line.startswith("http") and meta:
                if not skip:
                    base, quality, flags = split_name(meta[0])
                    attrs = meta[1]
                    if not any("not 24/7" in f.lower() for f in flags):
                        grp = (attrs.get("group-title") or "").split(";")[0].strip()
                        out.append({
                            "name": base, "quality": quality, "flags": flags,
                            "stream_url": line, "is_online": True,
                            "category": categorize(base, fallback=grp if grp and grp != "Undefined" else None),
                            "logo": attrs.get("tvg-logo", ""),
                            "tvg_id": attrs.get("tvg-id", ""),
                            "source": "iptv-org",
                        })
                meta = None
        logger.info(f"iptv-org: {len(out)} channels")
        return out
