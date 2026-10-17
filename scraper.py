#!/usr/bin/env python3
"""
India IPTV Playlist Generator
Scrapes IPTVCat for India channels, generates M3U playlist with EPG
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import time
import logging
from datetime import datetime
from urllib.parse import urljoin, urlparse
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────

BASE_URL = "https://iptvcat.com"
INDIA_URL = "https://iptvcat.com/india"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://iptvcat.com/",
}

# Free proxy/VPN services for geo-blocked content bypass
PROXY_SERVICES = [
    # Add your preferred proxy here, e.g.:
    # "socks5://user:pass@your-proxy.com:1080"
    # "http://proxy.example.com:8080"
]

# EPG sources for India
EPG_SOURCES = [
    {
        "name": "EPGSHARE01",
        "url": "https://epgshare01.online/epgshare01/epg_ripper_IN1.xml.gz",
        "description": "India EPG - Primary"
    },
    {
        "name": "M3UFREE",
        "url": "https://www.open-epg.com/files/india1.xml",
        "description": "India EPG - Secondary"
    },
    {
        "name": "Hoopla",
        "url": "http://epg.hoopla.tv/india.xml",
        "description": "India EPG - Tertiary"
    }
]

# Channel category mappings
CATEGORY_KEYWORDS = {
    "News": ["news", "ndtv", "aaj tak", "india today", "zee news", "republic",
             "times now", "cnbc", "mirror now", "tv9", "news18", "wion",
             "dd news", "loksabha", "rajyasabha"],
    "Entertainment": ["star plus", "zee tv", "sony", "colors", "life ok",
                      "sab tv", "star one", "imagine", "bindass", "&tv",
                      "star utsav", "zee anmol", "rishtey"],
    "Movies": ["star gold", "zee cinema", "sony max", "b4u movies", "movie",
               "cinema", "films", "zee bollywood", "& pictures", "set max",
               "mastii", "hit movies", "movies now", "romedy now", "mca"],
    "Sports": ["star sports", "sony six", "sony ten", "dd sports", "eurosport",
               "sony esp", "sports", "cricket", "kabaddi", "sony liv"],
    "Kids": ["cartoon", "disney", "nick", "nickelodeon", "pogo", "hungama",
             "discovery kids", "cbeebies", "baby tv", "kids"],
    "Music": ["mtv", "vh1", "9xm", "9x", "zing", "music", "b4u music",
              "eros now music", "zee music"],
    "Devotional": ["aastha", "sanskar", "ishwar", "sadhna", "divya", "god",
                   "bhakti", "spiritual", "peace", "qtv", "mta"],
    "Regional - Tamil": ["sun tv", "vijay", "kalaignar", "puthiya", "jaya",
                         "captain", "raj tv", "star vijay", "kolam", "tamil"],
    "Regional - Telugu": ["gemini", "maa tv", "tv9 telugu", "ntv", "hmtv",
                          "etv telugu", "zee telugu", "star maa", "telugu"],
    "Regional - Malayalam": ["asianet", "surya", "mazhavil", "flowers", "safari",
                              "reporter", "media one", "kerala", "malayalam"],
    "Regional - Kannada": ["star suvarna", "zee kannada", "colors kannada",
                           "udaya", "kasturi", "suvarna", "kannada"],
    "Regional - Bengali": ["star jalsha", "zee bangla", "sony aath", "colors",
                           "bengali", "bangla"],
    "Regional - Marathi": ["star pravah", "zee marathi", "colors marathi",
                           "sony marathi", "saam", "marathi"],
    "Regional - Gujarati": ["dd girnar", "gujarati", "vtv", "zee 24 kalak"],
    "Regional - Punjabi": ["ptc", "punjabi", "mh1"],
    "Infotainment": ["discovery", "nat geo", "national geographic", "history",
                     "animal planet", "tlc", "travel", "food", "living"],
    "English": ["bbc", "cnn", "fox", "espn", "hbo", "star world", "zee café",
                "movies now", "romedy", "wion english"],
    "General": []  # fallback
}


# ─── Scraper ──────────────────────────────────────────────────────────────────

class IPTVCatScraper:
    def __init__(self, use_proxy=False):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.use_proxy = use_proxy
        if use_proxy and PROXY_SERVICES:
            proxy = PROXY_SERVICES[0]
            self.session.proxies = {"http": proxy, "https": proxy}
            logger.info(f"Using proxy: {proxy}")

    def fetch_page(self, url, retries=3):
        for attempt in range(retries):
            try:
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                return resp.text
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed for {url}: {e}")
                time.sleep(2 ** attempt)
        return None

    def get_all_pages(self):
        """Get all pagination pages for India"""
        pages = [INDIA_URL]
        html = self.fetch_page(INDIA_URL)
        if not html:
            return pages
        soup = BeautifulSoup(html, "html.parser")
        # Find pagination links
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if "india" in href.lower() and ("page" in href.lower() or re.search(r'/\d+', href)):
                full = urljoin(BASE_URL, href)
                if full not in pages:
                    pages.append(full)
        return pages

    def parse_channels(self, html):
        """Parse channel entries from page HTML"""
        channels = []
        soup = BeautifulSoup(html, "html.parser")

        # IPTVCat table rows
        rows = soup.select("table tbody tr") or soup.select(".channel-list tr")
        
        if not rows:
            # Try alternative selectors
            rows = soup.find_all("tr")

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 3:
                continue

            try:
                # Extract channel name
                name_el = cols[0].find("a") or cols[0]
                name = name_el.get_text(strip=True)

                # Extract stream URL - look for M3U8 links
                stream_url = None
                for col in cols:
                    links = col.find_all("a", href=True)
                    for link in links:
                        href = link["href"]
                        if any(x in href.lower() for x in [".m3u8", ".ts", "stream", "live"]):
                            stream_url = href if href.startswith("http") else urljoin(BASE_URL, href)
                            break
                    if stream_url:
                        break

                # Try to find stream URL in data attributes
                if not stream_url:
                    for el in row.find_all(attrs={"data-url": True}):
                        stream_url = el["data-url"]
                        break

                # Extract channel detail page link to get actual stream
                detail_link = None
                for a in row.find_all("a", href=True):
                    if "channel" in a["href"].lower() or name.lower().replace(" ", "-") in a["href"].lower():
                        detail_link = urljoin(BASE_URL, a["href"])
                        break

                if not name or (not stream_url and not detail_link):
                    continue

                # Status
                status_el = row.find(class_=re.compile("online|offline|status", re.I))
                is_online = True
                if status_el:
                    is_online = "online" in status_el.get("class", []) or \
                                "online" in status_el.get_text().lower()

                channels.append({
                    "name": name,
                    "stream_url": stream_url,
                    "detail_link": detail_link,
                    "is_online": is_online,
                    "category": self.categorize(name),
                    "logo": self.find_logo(row, name),
                    "tvg_id": self.make_tvg_id(name),
                })
            except Exception as e:
                logger.debug(f"Error parsing row: {e}")
                continue

        return channels

    def fetch_stream_from_detail(self, url):
        """Visit channel detail page to extract the actual stream URL"""
        html = self.fetch_page(url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")

        # Look for M3U8 in scripts
        scripts = soup.find_all("script")
        for script in scripts:
            text = script.string or ""
            urls = re.findall(r'(https?://[^\s\'"]+\.m3u8[^\s\'"]*)', text)
            if urls:
                return urls[0]
            # Also look for source/stream vars
            matches = re.findall(r'(?:source|stream|url|src)["\s]*[:=]["\s]*(https?://[^\s\'"]+)', text)
            for m in matches:
                if any(x in m for x in [".m3u8", "/live", "/stream", ".ts"]):
                    return m

        # Look in video/source tags
        for tag in soup.select("video source, source"):
            src = tag.get("src", "")
            if src and ("m3u8" in src or "stream" in src):
                return src

        # Look in iframes
        for iframe in soup.select("iframe"):
            src = iframe.get("src", "")
            if src:
                sub_html = self.fetch_page(src)
                if sub_html:
                    urls = re.findall(r'(https?://[^\s\'"]+\.m3u8[^\s\'"]*)', sub_html)
                    if urls:
                        return urls[0]

        return None

    def find_logo(self, row, name):
        """Try to find channel logo URL"""
        img = row.find("img")
        if img:
            src = img.get("src") or img.get("data-src", "")
            if src:
                return urljoin(BASE_URL, src)
        # Fallback: use a logo API
        slug = re.sub(r'[^a-z0-9]', '-', name.lower()).strip('-')
        return f"https://raw.githubusercontent.com/uddhavz/iptv-logos/main/logos/{slug}.png"

    def categorize(self, name):
        name_lower = name.lower()
        for category, keywords in CATEGORY_KEYWORDS.items():
            if category == "General":
                continue
            for kw in keywords:
                if kw in name_lower:
                    return category
        return "General"

    def make_tvg_id(self, name):
        return re.sub(r'[^a-zA-Z0-9]', '', name).lower()

    def scrape(self, max_pages=5, only_online=True):
        logger.info("Starting scrape of IPTVCat India...")
        all_channels = []
        pages = self.get_all_pages()
        pages = pages[:max_pages]

        for i, page_url in enumerate(pages):
            logger.info(f"Scraping page {i+1}/{len(pages)}: {page_url}")
            html = self.fetch_page(page_url)
            if not html:
                continue
            channels = self.parse_channels(html)
            logger.info(f"  Found {len(channels)} channels on this page")

            # Fetch actual stream URLs from detail pages
            for ch in channels:
                if not ch["stream_url"] and ch["detail_link"]:
                    logger.debug(f"  Fetching stream for: {ch['name']}")
                    ch["stream_url"] = self.fetch_stream_from_detail(ch["detail_link"])
                    time.sleep(0.5)  # Be polite

            all_channels.extend(channels)
            time.sleep(1)

        # Filter
        if only_online:
            before = len(all_channels)
            all_channels = [c for c in all_channels if c["is_online"] and c["stream_url"]]
            logger.info(f"Filtered to {len(all_channels)} online channels (from {before})")
        else:
            all_channels = [c for c in all_channels if c["stream_url"]]

        # Deduplicate by stream URL
        seen = set()
        unique = []
        for ch in all_channels:
            if ch["stream_url"] not in seen:
                seen.add(ch["stream_url"])
                unique.append(ch)

        logger.info(f"Final unique channels: {len(unique)}")
        return unique
