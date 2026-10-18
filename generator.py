#!/usr/bin/env python3
"""Playlist generator - M3U (SS IPTV friendly), JSON index and README."""

import re
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

EPG_SOURCES = [
    "https://epgshare01.online/epgshare01/epg_ripper_IN1.xml.gz",
    "https://www.open-epg.com/files/india1.xml",
    "https://raw.githubusercontent.com/iptv-org/epg/gh-pages/guides/in.epg.xml",
]

# name (lowercase) -> tvg-id used for EPG matching
KNOWN_TVG_IDS = {
    "star plus": "StarPlus.in", "star gold": "StarGold.in", "star world": "StarWorld.in",
    "star sports 1": "StarSports1.in", "star sports 2": "StarSports2.in",
    "star sports 3": "StarSports3.in", "star sports first": "StarSportsFirst.in",
    "star maa": "StarMaa.in", "star vijay": "StarVijay.in", "star suvarna": "StarSuvarna.in",
    "star jalsha": "StarJalsha.in", "star pravah": "StarPravah.in",
    "zee tv": "ZeeTV.in", "zee cinema": "ZeeCinema.in", "zee news": "ZeeNews.in",
    "zee cafe": "ZeeCafe.in", "zee café": "ZeeCafe.in", "zee bollywood": "ZeeBollywood.in",
    "zee anmol": "ZeeAnmol.in", "zee bangla": "ZeeBangla.in", "zee marathi": "ZeeMarathi.in",
    "zee kannada": "ZeeKannada.in", "zee telugu": "ZeeTelugu.in", "zee tamil": "ZeeTamil.in",
    "sony max": "SonyMax.in", "sony max 2": "SonyMax2.in", "sony six": "SonySix.in",
    "sony ten 1": "SonyTen1.in", "sony ten 2": "SonyTen2.in", "sony ten 3": "SonyTen3.in",
    "sony ten 4": "SonyTen4.in", "sony ten 5": "SonyTen5.in", "sony sab": "SonySab.in",
    "sony aath": "SonyAath.in", "set india": "SonyEntertainmentTelevision.in",
    "colors": "Colors.in", "colors cineplex": "ColorsCineplex.in",
    "colors infinity": "ColorsInfinity.in", "colors kannada": "ColorsKannada.in",
    "colors marathi": "ColorsMarathi.in", "colors bangla": "ColorsBangla.in",
    "colors gujarati": "ColorsGujarati.in",
    "ndtv 24x7": "NDTV24x7.in", "ndtv india": "NDTVIndia.in", "ndtv profit": "NDTVProfit.in",
    "aaj tak": "AajTak.in", "india today": "IndiaToday.in", "republic tv": "RepublicTV.in",
    "republic bharat": "RepublicBharat.in", "times now": "TimesNow.in",
    "mirror now": "MirrorNow.in", "cnbc tv18": "CNBCTV18.in", "cnbc awaaz": "CNBCAwaaz.in",
    "news18 india": "News18India.in", "wion": "WION.in",
    "dd national": "DDNational.in", "dd news": "DDNews.in", "dd india": "DDIndia.in",
    "dd sports": "DDSports.in",
    "sun tv": "SunTV.in", "kalaignar": "Kalaignar.in", "vijay tv": "VijayTV.in",
    "gemini tv": "GeminiTV.in", "maa tv": "MaaTV.in", "asianet": "Asianet.in",
    "surya tv": "SuryaTV.in", "mazhavil manorama": "MazhavilManorama.in",
    "flowers tv": "FlowersTV.in", "media one": "MediaOne.in",
    "discovery": "Discovery.in", "discovery science": "DiscoveryScience.in",
    "animal planet": "AnimalPlanet.in", "national geographic": "NationalGeographic.in",
    "history tv18": "HistoryTV18.in", "tlc": "TLC.in",
    "disney channel": "DisneyChannel.in", "disney junior": "DisneyJunior.in",
    "cartoon network": "CartoonNetwork.in", "nickelodeon": "Nickelodeon.in", "pogo": "Pogo.in",
    "mtv": "MTV.in", "vh1": "VH1.in", "9xm": "9XM.in",
    "b4u movies": "B4UMovies.in", "b4u music": "B4UMusic.in",
    "aastha": "Aastha.in", "sanskar": "SanskarTV.in",
}
_KEYS_LONGEST_FIRST = sorted(KNOWN_TVG_IDS, key=len, reverse=True)


def slugify(text):
    """Safe file-name slug, shared by generator and README so links always match."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "general"


def attr(text):
    """Make a value safe inside an M3U attribute."""
    return re.sub(r"\s+", " ", str(text)).replace('"', "'").strip()


class PlaylistGenerator:
    def __init__(self, output_dir="output", repo=None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.repo = repo  # "user/repo" for README links

    def get_tvg_id(self, channel_name):
        name = re.sub(r"\s+", " ", channel_name.lower()).strip()
        if name in KNOWN_TVG_IDS:
            return KNOWN_TVG_IDS[name]
        for key in _KEYS_LONGEST_FIRST:
            if re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(key), name):
                return KNOWN_TVG_IDS[key]
        return re.sub(r"[^A-Za-z0-9]", "", channel_name)

    def generate_m3u(self, channels, filename="india_iptv.m3u"):
        """SS IPTV compatible M3U: plain header, one EXTINF + optional EXTGRP + URL per channel."""
        lines = [f'#EXTM3U url-tvg="{",".join(EPG_SOURCES[:2])}"']
        ordered = sorted(channels, key=lambda c: (c.get("category", "General"), c.get("name", "").lower()))
        count = 0
        for ch in ordered:
            url = (ch.get("stream_url") or "").strip()
            if not url:
                continue
            name = attr(ch.get("name", "Unknown")) or "Unknown"
            cat = attr(ch.get("category", "General"))
            logo = attr(ch.get("logo", ""))
            tvg_id = attr(ch.get("tvg_id") or self.get_tvg_id(name))
            extinf = f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{name}"'
            if logo:
                extinf += f' tvg-logo="{logo}"'
            extinf += f' group-title="{cat}",{name}'
            lines += [extinf, f"#EXTGRP:{cat}", url]
            count += 1

        path = self.output_dir / filename
        # utf-8 with LF endings; no comments between entries (some TV parsers choke on them)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info(f"M3U saved: {path} ({count} channels)")
        return str(path)

    def generate_m3u_by_category(self, channels):
        groups = defaultdict(list)
        for ch in channels:
            groups[ch.get("category", "General")].append(ch)
        files = []
        for cat, chans in groups.items():
            fname = f"india_{slugify(cat)}.m3u"
            files.append((cat, self.generate_m3u(chans, fname), len(chans), fname))
        return files

    def generate_json_index(self, channels, filename="channels.json"):
        cats = defaultdict(list)
        for ch in channels:
            cats[ch.get("category", "General")].append({
                "name": ch["name"], "url": ch["stream_url"], "logo": ch.get("logo", ""),
                "tvg_id": ch.get("tvg_id") or self.get_tvg_id(ch["name"]), "is_online": ch.get("is_online", True),
            })
        index = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_channels": len(channels),
            "epg_sources": EPG_SOURCES,
            "categories": {c: {"count": len(v), "channels": v} for c, v in sorted(cats.items())},
        }
        path = self.output_dir / filename
        path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"JSON index saved: {path}")
        return str(path)

    def generate_readme(self, channels, filename="README.md"):
        cats = defaultdict(list)
        for ch in channels:
            cats[ch.get("category", "General")].append(ch["name"])

        base = (f"https://raw.githubusercontent.com/{self.repo}/main/output"
                if self.repo else "https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/output")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        L = [
            "# 🇮🇳 India IPTV Playlist\n\n",
            f"**Auto-generated:** {now}  \n**Total channels:** {len(channels)}\n\n---\n\n",
            "## 📺 Playlists\n\n| Playlist | Channels | File |\n|---|---|---|\n",
            f"| All India | {len(channels)} | [india_iptv.m3u](output/india_iptv.m3u) |\n",
        ]
        for cat, names in sorted(cats.items()):
            f = f"india_{slugify(cat)}.m3u"
            L.append(f"| {cat} | {len(names)} | [{f}](output/{f}) |\n")

        L += [
            "\n---\n\n## 📡 SS IPTV (Samsung / LG smart TV)\n\n",
            "1. Push this repo to GitHub.\n",
            f"2. Your playlist URL is:\n   `{base}/india_iptv.m3u`\n",
            "3. On the TV open **SS IPTV → Settings → Content → External playlists → Add**.\n",
            "4. Enter a name and paste the URL, save, then go back to the main screen.\n",
            "5. Alternative: Settings → General → *Get code*, then upload the .m3u from "
            "the SS IPTV site's *Edit* page.\n\n"
            "EPG: SS IPTV reads `url-tvg` from the playlist header; you can also set it in "
            "Settings → EPG.\n\n",
            "### Other players (VLC / TiviMate / Kodi)\n\n",
            "Add the same M3U URL. EPG URLs:\n\n",
        ]
        L += [f"- `{s}`\n" for s in EPG_SOURCES]
        L += ["\n---\n\n## 📋 Channel list\n\n"]
        for cat, names in sorted(cats.items()):
            L.append(f"### {cat}\n\n")
            L += [f"- {n}\n" for n in sorted(set(names))]
            L.append("\n")
        L.append("---\n\n*For personal use. Free streams change often - rerun the script regularly.*\n")

        path = self.output_dir.parent / filename
        path.write_text("".join(L), encoding="utf-8")
        logger.info(f"README saved: {path}")
        return str(path)
