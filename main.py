#!/usr/bin/env python3
"""
India IPTV Playlist Generator - Main Entry Point
Usage: python main.py [--proxy] [--all] [--no-filter]
"""

import argparse
import sys
import os
from pathlib import Path

# ── Create directories FIRST before any logging setup ──
Path("logs").mkdir(exist_ok=True)
Path("output").mkdir(exist_ok=True)
Path("docs").mkdir(exist_ok=True)
Path("scripts").mkdir(exist_ok=True)

import logging

# Setup logging AFTER directories exist
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/scraper.log", mode="a"),
    ]
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="India IPTV Playlist Generator")
    parser.add_argument("--proxy", action="store_true", help="Use proxy for geo-blocked channels")
    parser.add_argument("--all", action="store_true", help="Include offline channels")
    parser.add_argument("--pages", type=int, default=5, help="Max pages to scrape (default: 5)")
    parser.add_argument("--no-split", action="store_true", help="Don't generate per-category playlists")
    parser.add_argument("--no-cf-worker", action="store_true", help="Skip generating Cloudflare Worker file")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("🇮🇳 India IPTV Playlist Generator Starting")
    logger.info("=" * 60)

    # Import modules
    from scraper import IPTVCatScraper
    from generator import PlaylistGenerator
    from geobypass import apply_proxy_to_channels, generate_cloudflare_worker, generate_streamlink_script

    # Step 1: Generate Cloudflare Worker (for geo-bypass setup)
    if not args.no_cf_worker:
        logger.info("\n📦 Generating Cloudflare Worker for geo-bypass...")
        generate_cloudflare_worker()
        generate_streamlink_script([], output_path="scripts/play_channel.sh")

    # Step 2: Scrape channels
    logger.info("\n🔍 Scraping IPTVCat India channels...")
    scraper = IPTVCatScraper(use_proxy=args.proxy)
    channels = scraper.scrape(
        max_pages=args.pages,
        only_online=not args.all
    )

    if not channels:
        logger.error("No channels found! Check the scraper or try again later.")
        sys.exit(1)

    logger.info(f"\n✅ Scraped {len(channels)} channels")

    # Step 3: Apply geo-bypass proxy to relevant channels
    logger.info("\n🌐 Applying geo-bypass configuration...")
    channels = apply_proxy_to_channels(channels)

    # Step 4: Generate playlists
    logger.info("\n📝 Generating playlists...")
    gen = PlaylistGenerator(output_dir="output")

    # Main all-channels playlist
    m3u_path = gen.generate_m3u(channels, filename="india_iptv.m3u")
    logger.info(f"  ✅ Main playlist: {m3u_path}")

    # Per-category playlists
    if not args.no_split:
        logger.info("  📂 Generating per-category playlists...")
        cat_files = gen.generate_m3u_by_category(channels)

    # JSON index
    json_path = gen.generate_json_index(channels)
    logger.info(f"  ✅ JSON index: {json_path}")

    # README
    readme_path = gen.generate_readme(channels)
    logger.info(f"  ✅ README: {readme_path}")

    # Step 5: Summary
    from collections import Counter
    cat_counts = Counter(ch.get("category", "General") for ch in channels)

    logger.info("\n" + "=" * 60)
    logger.info("📊 SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total channels: {len(channels)}")
    logger.info("\nBy category:")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {cat:<30} {count:>3} channels")

    logger.info("\n📁 Output files:")
    logger.info(f"  output/india_iptv.m3u         - Main playlist")
    logger.info(f"  output/channels.json           - Channel index")
    logger.info(f"  output/india_*.m3u             - Per-category playlists")
    logger.info(f"  docs/cloudflare_worker.js      - Geo-bypass worker")
    logger.info(f"  scripts/play_channel.sh        - Streamlink script")
    logger.info(f"  README.md                      - Documentation")

    logger.info("\n✅ Done! Push to GitHub to serve your playlists.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
