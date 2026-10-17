#!/usr/bin/env python3
"""
Geo-Block Bypass Module
Wraps geo-blocked stream URLs with proxy/tunnel solutions for personal use
"""

import re
import logging
import os

logger = logging.getLogger(__name__)

# ─── Proxy Configuration ──────────────────────────────────────────────────────
#
# Option 1: Cloudflare Workers proxy (free, self-hosted)
#   Deploy the worker from docs/cloudflare_worker.js to your CF account
#   Set CLOUDFLARE_WORKER_URL env var
#
# Option 2: Personal VPS with 3proxy or Squid
#   Set PROXY_URL env var to your proxy URL
#   e.g., socks5://user:pass@your-vps.com:1080
#
# Option 3: Residential proxy service
#   Set PROXY_URL env var
#
# Option 4: Wireguard/OpenVPN with India exit node
#   Run the player device on VPN, no URL modification needed

CLOUDFLARE_WORKER_URL = os.getenv("CLOUDFLARE_WORKER_URL", "")
PROXY_URL = os.getenv("PROXY_URL", "")

# Known geo-blocked domains (India-only or restricted)
GEO_BLOCKED_PATTERNS = [
    r"hotstar",
    r"jiocinema",
    r"sonyliv",
    r"zee5",
    r"voot",
    r"mxplayer",
    r"erosnow",
    r"altbalaji",
    r"discovery\+",
    r"sunnxt",
]

# Free public proxies for M3U8 streams (stream proxies, not web proxies)
# These wrap the HLS stream so it plays from an allowed region
FREE_STREAM_PROXIES = [
    # Format: "https://proxy-base-url.com/proxy?url={url}"
    # Uncomment and add your proxy services:
    # "https://your-worker.your-subdomain.workers.dev/?url={url}",
    # "https://your-vps.com:8080/proxy?url={url}",
]


def is_geo_blocked(url):
    """Check if URL is likely geo-blocked"""
    url_lower = url.lower()
    for pattern in GEO_BLOCKED_PATTERNS:
        if re.search(pattern, url_lower):
            return True
    return False


def wrap_with_proxy(url):
    """Wrap a stream URL with a proxy service"""
    if CLOUDFLARE_WORKER_URL:
        return f"{CLOUDFLARE_WORKER_URL.rstrip('/')}/?url={url}"
    if PROXY_URL and "socks" not in PROXY_URL and "http" in PROXY_URL:
        # HTTP proxy that can forward streams
        return f"{PROXY_URL.rstrip('/')}/proxy?url={url}"
    if FREE_STREAM_PROXIES:
        return FREE_STREAM_PROXIES[0].format(url=url)
    return url  # Return original if no proxy configured


def generate_streamlink_script(channels, output_path="scripts/play_channel.sh"):
    """
    Generate a Streamlink script for geo-blocked channels.
    Streamlink can use proxies to bypass geo-restrictions.
    """
    script = """#!/bin/bash
# India IPTV - Streamlink Player Script
# Plays geo-blocked channels via proxy/VPN

# Configuration
PROXY="${SOCKS_PROXY:-}"  # Set your SOCKS5 proxy: user:pass@host:port
VLC_CMD="${VLC:-vlc}"

CHANNEL_URL="$1"
QUALITY="${2:-best}"

if [ -z "$CHANNEL_URL" ]; then
    echo "Usage: $0 <channel_url> [quality]"
    echo "Example: $0 https://example.com/stream.m3u8 best"
    exit 1
fi

echo "Playing: $CHANNEL_URL"
echo "Quality: $QUALITY"

if [ -n "$PROXY" ]; then
    echo "Using proxy: $PROXY"
    streamlink \\
        --socks-proxy "socks5://$PROXY" \\
        --player "$VLC_CMD" \\
        "$CHANNEL_URL" \\
        "$QUALITY"
else
    streamlink \\
        --player "$VLC_CMD" \\
        "$CHANNEL_URL" \\
        "$QUALITY"
fi
"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(script)
    os.chmod(output_path, 0o755)
    logger.info(f"Streamlink script saved: {output_path}")


def apply_proxy_to_channels(channels):
    """
    Modify geo-blocked channel URLs to route through proxy.
    Only modifies if proxy is configured.
    """
    if not (CLOUDFLARE_WORKER_URL or PROXY_URL or FREE_STREAM_PROXIES):
        logger.info("No proxy configured. Geo-blocked channels will play directly.")
        logger.info("Set CLOUDFLARE_WORKER_URL or PROXY_URL env vars to enable bypass.")
        return channels

    modified = 0
    for ch in channels:
        url = ch.get("stream_url", "")
        if url and is_geo_blocked(url):
            ch["stream_url"] = wrap_with_proxy(url)
            ch["name"] = ch["name"]  # keep name
            modified += 1

    logger.info(f"Applied proxy to {modified} potentially geo-blocked channels")
    return channels


def generate_cloudflare_worker():
    """Generate Cloudflare Worker JavaScript for stream proxying"""
    js = """// Cloudflare Worker - IPTV Stream Proxy
// Deploy at: https://workers.cloudflare.com/
// For PERSONAL USE ONLY

addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request))
})

async function handleRequest(request) {
  const url = new URL(request.url)
  const targetUrl = url.searchParams.get('url')

  if (!targetUrl) {
    return new Response('Usage: ?url=https://stream-url.m3u8', { status: 400 })
  }

  // CORS headers for media players
  const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  }

  if (request.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders })
  }

  try {
    // Forward request with India-region headers
    const response = await fetch(targetUrl, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': new URL(targetUrl).origin + '/',
        'Origin': new URL(targetUrl).origin,
        ...Object.fromEntries(request.headers),
      },
    })

    // If M3U8, rewrite segment URLs to go through proxy too
    const contentType = response.headers.get('Content-Type') || ''
    if (contentType.includes('mpegurl') || targetUrl.endsWith('.m3u8')) {
      let text = await response.text()
      const baseUrl = targetUrl.substring(0, targetUrl.lastIndexOf('/') + 1)
      
      // Rewrite relative URLs in M3U8 to absolute, routed through proxy
      text = text.replace(/^(?!#)([^\\n]+\\.ts[^\\n]*)/gm, (match) => {
        if (match.startsWith('http')) {
          return `${url.origin}/?url=${encodeURIComponent(match)}`
        } else {
          return `${url.origin}/?url=${encodeURIComponent(baseUrl + match)}`
        }
      })
      
      // Also rewrite sub-playlist URLs
      text = text.replace(/^(?!#)([^\\n]+\\.m3u8[^\\n]*)/gm, (match) => {
        if (match.startsWith('http')) {
          return `${url.origin}/?url=${encodeURIComponent(match)}`
        } else {
          return `${url.origin}/?url=${encodeURIComponent(baseUrl + match)}`
        }
      })

      return new Response(text, {
        status: response.status,
        headers: {
          ...corsHeaders,
          'Content-Type': 'application/vnd.apple.mpegurl',
          'Cache-Control': 'no-cache',
        },
      })
    }

    // For other content (TS segments etc), stream directly
    return new Response(response.body, {
      status: response.status,
      headers: {
        ...corsHeaders,
        'Content-Type': contentType || 'video/mp2t',
        'Cache-Control': 'no-cache',
      },
    })

  } catch (err) {
    return new Response(`Error: ${err.message}`, { 
      status: 500, 
      headers: corsHeaders 
    })
  }
}
"""
    os.makedirs("docs", exist_ok=True)
    with open("docs/cloudflare_worker.js", "w") as f:
        f.write(js)
    logger.info("Cloudflare Worker saved: docs/cloudflare_worker.js")
    return js
