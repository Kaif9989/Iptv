#!/usr/bin/env python3
"""
Playlist Generator - Creates M3U and EPG XML files from scraped channels
"""

import os
import json
import gzip
import logging
import requests
from datetime import datetime
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring, indent
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

# ─── EPG Sources ──────────────────────────────────────────────────────────────

EPG_SOURCES = [
    "https://epgshare01.online/epgshare01/epg_ripper_IN1.xml.gz",
    "https://www.open-epg.com/files/india1.xml",
    "https://raw.githubusercontent.com/iptv-org/epg/gh-pages/guides/in.epg.xml",
    "https://raw.githubusercontent.com/azimjon-95/tvgraber/main/in.xml",
]

# TVG-ID mappings for known India channels (for EPG matching)
KNOWN_TVG_IDS = {
    "star plus": "StarPlus.in",
    "star gold": "StarGold.in",
    "star world": "StarWorld.in",
    "star sports 1": "StarSports1.in",
    "star sports 2": "StarSports2.in",
    "star sports 3": "StarSports3.in",
    "star sports first": "StarSportsFirst.in",
    "star maa": "StarMaa.in",
    "star vijay": "StarVijay.in",
    "star suvarna": "StarSuvarna.in",
    "zee tv": "ZeeTV.in",
    "zee cinema": "ZeeCinema.in",
    "zee news": "ZeeNews.in",
    "zee5": "Zee5.in",
    "zee café": "ZeeCafe.in",
    "zee bollywood": "ZeeBollywood.in",
    "zee anmol": "ZeeAnmol.in",
    "zee bangla": "ZeeBangla.in",
    "zee marathi": "ZeeMarathi.in",
    "zee kannada": "ZeeKannada.in",
    "zee telugu": "ZeeTelugu.in",
    "sony max": "SonyMax.in",
    "sony max 2": "SonyMax2.in",
    "sony six": "SonySix.in",
    "sony ten 1": "SonyTen1.in",
    "sony ten 2": "SonyTen2.in",
    "sony ten 3": "SonyTen3.in",
    "sony ten 4": "SonyTen4.in",
    "sony ten 5": "SonyTen5.in",
    "set india": "SonyEntertainmentTelevision.in",
    "sony sab": "SonySab.in",
    "sony aath": "SonyAath.in",
    "sony liv": "SonyLIV.in",
    "colors": "Colors.in",
    "colors cineplex": "ColorsCineplex.in",
    "colors infinity": "ColorsInfinity.in",
    "colors kannada": "ColorsKannada.in",
    "colors marathi": "ColorsMarathi.in",
    "colors bangla": "ColorsBangla.in",
    "colors gujarati": "ColorsGujarati.in",
    "ndtv 24x7": "NDTV24x7.in",
    "ndtv india": "NDTVIndia.in",
    "ndtv profit": "NDTVProfit.in",
    "aaj tak": "AajTak.in",
    "india today": "IndiaToday.in",
    "republic tv": "RepublicTV.in",
    "republic bharat": "RepublicBharat.in",
    "times now": "TimesNow.in",
    "mirror now": "MirrorNow.in",
    "cnbc tv18": "CNBCTV18.in",
    "cnbc awaaz": "CNBCAwaaz.in",
    "news18 india": "News18India.in",
    "wion": "WION.in",
    "dd national": "DDNational.in",
    "dd news": "DDNews.in",
    "dd india": "DDIndia.in",
    "dd sports": "DDSports.in",
    "sun tv": "SunTV.in",
    "kalaignar": "Kalaignar.in",
    "vijay tv": "VijayTV.in",
    "zee tamil": "ZeeTamil.in",
    "gemini tv": "GeminiTV.in",
    "zee telugu": "ZeeTelugu.in",
    "maa tv": "MaaTV.in",
    "asianet": "Asianet.in",
    "surya tv": "SuryaTV.in",
    "mazhavil manorama": "MazhavilManorama.in",
    "flowers tv": "FlowersTV.in",
    "media one": "MediaOne.in",
    "star jalsha": "StarJalsha.in",
    "star pravah": "StarPravah.in",
    "discovery": "Discovery.in",
    "discovery science": "DiscoveryScience.in",
    "animal planet": "AnimalPlanet.in",
    "nat geo": "NatGeoWild.in",
    "national geographic": "NationalGeographic.in",
    "history tv18": "HistoryTV18.in",
    "tlc india": "TLC.in",
    "disney channel": "DisneyChannel.in",
    "disney junior": "DisneyJunior.in",
    "cartoon network": "CartoonNetwork.in",
    "nickelodeon": "Nickelodeon.in",
    "pogo": "Pogo.in",
    "mtv india": "MTV.in",
    "vh1 india": "VH1.in",
    "9xm": "9XM.in",
    "b4u movies": "B4UMovies.in",
    "b4u music": "B4UMusic.in",
    "aastha": "Aastha.in",
    "sanskar": "SanskarTV.in",
}


class PlaylistGenerator:
    def __init__(self, output_dir="output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def get_tvg_id(self, channel_name):
        name_lower = channel_name.lower().strip()
        for key, tvg_id in KNOWN_TVG_IDS.items():
            if key in name_lower or name_lower in key:
                return tvg_id
        return channel_name.replace(" ", "")

    def generate_m3u(self, channels, filename="india_iptv.m3u"):
        """Generate M3U8 playlist"""
        # EPG URL string
        epg_urls = " ".join([f'url-tvg="{u}"' for u in EPG_SOURCES[:2]])

        lines = [
            f'#EXTM3U x-tvg-url="{EPG_SOURCES[0]}" '
            f'url-tvg="{EPG_SOURCES[1]}" '
            f'refresh="3600"\n',
        ]

        # Sort by category then name
        sorted_channels = sorted(channels, key=lambda x: (x.get("category", "General"), x.get("name", "")))

        current_cat = None
        for ch in sorted_channels:
            cat = ch.get("category", "General")
            name = ch.get("name", "Unknown")
            stream_url = ch.get("stream_url", "")
            logo = ch.get("logo", "")
            tvg_id = self.get_tvg_id(name)

            if not stream_url:
                continue

            # Add category separator comment
            if cat != current_cat:
                lines.append(f"\n# ═══ {cat} ═══\n")
                current_cat = cat

            # EXTINF line
            extinf = (
                f'#EXTINF:-1 tvg-id="{tvg_id}" '
                f'tvg-name="{name}" '
                f'tvg-logo="{logo}" '
                f'group-title="{cat}"'
                f',{name}\n'
            )
            lines.append(extinf)
            lines.append(f"{stream_url}\n")

        output_path = self.output_dir / filename
        with open(output_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        logger.info(f"M3U playlist saved: {output_path} ({len(sorted_channels)} channels)")
        return str(output_path)

    def generate_m3u_by_category(self, channels):
        """Generate separate M3U file for each category"""
        from collections import defaultdict
        cat_channels = defaultdict(list)
        for ch in channels:
            cat_channels[ch.get("category", "General")].append(ch)

        files = []
        for cat, chans in cat_channels.items():
            safe_cat = re.sub(r'[^\w\- ]', '', cat).strip().replace(" ", "_")
            fname = f"india_{safe_cat.lower()}.m3u"
            path = self.generate_m3u(chans, filename=fname)
            files.append((cat, path, len(chans)))
            logger.info(f"  {cat}: {len(chans)} channels → {fname}")

        return files

    def generate_json_index(self, channels, filename="channels.json"):
        """Generate JSON index of all channels"""
        from collections import defaultdict
        index = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "total_channels": len(channels),
            "epg_sources": EPG_SOURCES,
            "categories": {},
        }

        cat_map = defaultdict(list)
        for ch in channels:
            cat_map[ch.get("category", "General")].append({
                "name": ch["name"],
                "url": ch["stream_url"],
                "logo": ch.get("logo", ""),
                "tvg_id": self.get_tvg_id(ch["name"]),
                "is_online": ch.get("is_online", True),
            })

        for cat, chans in sorted(cat_map.items()):
            index["categories"][cat] = {
                "count": len(chans),
                "channels": chans,
            }

        output_path = self.output_dir / filename
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

        logger.info(f"JSON index saved: {output_path}")
        return str(output_path)

    def generate_readme(self, channels, filename="README.md"):
        """Generate README with channel list and usage instructions"""
        from collections import defaultdict
        cat_map = defaultdict(list)
        for ch in channels:
            cat_map[ch.get("category", "General")].append(ch["name"])

        lines = [
            "# 🇮🇳 India IPTV Playlist\n\n",
            f"**Auto-generated on:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\n",
            f"**Total Channels:** {len(channels)}\n\n",
            "---\n\n",
            "## 📺 Quick Links\n\n",
            "| Playlist | Channels | Link |\n",
            "|----------|----------|------|\n",
            f"| 🇮🇳 All India | {len(channels)} | [india_iptv.m3u](output/india_iptv.m3u) |\n",
        ]

        for cat, chans in sorted(cat_map.items()):
            safe = cat.replace(" ", "_").lower()
            safe = re.sub(r'[^\w_]', '', safe)
            lines.append(f"| {cat} | {len(chans)} | [india_{safe}.m3u](output/india_{safe}.m3u) |\n")

        lines += [
            "\n---\n\n",
            "## 📡 EPG (Electronic Programme Guide)\n\n",
            "Add these EPG URLs to your player:\n\n",
        ]
        for src in EPG_SOURCES:
            lines.append(f"- `{src}`\n")

        lines += [
            "\n---\n\n",
            "## 🔧 How to Use\n\n",
            "### VLC Media Player\n",
            "1. Open VLC → Media → Open Network Stream\n",
            "2. Paste the raw GitHub URL of `india_iptv.m3u`\n\n",
            "### IPTV Smarters / TiviMate / OTT Navigator\n",
            "1. Add new playlist → M3U URL\n",
            "2. Paste: `https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/output/india_iptv.m3u`\n",
            "3. Add EPG: `https://epgshare01.online/epgshare01/epg_ripper_IN1.xml.gz`\n\n",
            "### Kodi (PVR IPTV Simple Client)\n",
            "1. Install PVR IPTV Simple Client addon\n",
            "2. Set M3U URL and EPG URL in settings\n\n",
            "---\n\n",
            "## 🌐 Geo-Blocked Channels\n\n",
            "Some channels may be geo-restricted. See [VPN Setup Guide](docs/vpn_setup.md) for bypass options.\n\n",
            "---\n\n",
            "## 📋 Channel List\n\n",
        ]

        for cat, chans in sorted(cat_map.items()):
            lines.append(f"### {cat}\n\n")
            for name in sorted(chans):
                lines.append(f"- {name}\n")
            lines.append("\n")

        lines += [
            "---\n\n",
            "*This playlist is for personal use only. Refresh every 24 hours.*\n",
        ]

        output_path = self.output_dir.parent / filename
        with open(output_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        logger.info(f"README saved: {output_path}")
        return str(output_path)


import re
