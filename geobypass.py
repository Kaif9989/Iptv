#!/usr/bin/env python3
"""
Optional proxy wrapper for streams that only play from certain regions.
Uses YOUR OWN Cloudflare Worker / proxy. Nothing is changed unless you set one:
    CLOUDFLARE_WORKER_URL=https://your-worker.workers.dev
    PROXY_URL=https://your-proxy.example.com:8080
Note: SS IPTV is happiest with plain HLS links; use a proxy only for channels that need it.
"""

import os
import re
import logging
from urllib.parse import quote

logger = logging.getLogger(__name__)

CLOUDFLARE_WORKER_URL = os.getenv("CLOUDFLARE_WORKER_URL", "")
PROXY_URL = os.getenv("PROXY_URL", "")

GEO_BLOCKED_PATTERNS = [r"hotstar", r"jiocinema", r"sonyliv", r"zee5", r"voot",
                        r"mxplayer", r"erosnow", r"altbalaji", r"discovery\+", r"sunnxt"]
FREE_STREAM_PROXIES = []  # e.g. "https://your-worker.workers.dev/?url={url}"


def is_geo_blocked(url):
    return any(re.search(p, url.lower()) for p in GEO_BLOCKED_PATTERNS)


def wrap_with_proxy(url):
    enc = quote(url, safe="")
    if CLOUDFLARE_WORKER_URL:
        return f"{CLOUDFLARE_WORKER_URL.rstrip('/')}/?url={enc}"
    if PROXY_URL and PROXY_URL.startswith("http"):
        return f"{PROXY_URL.rstrip('/')}/proxy?url={enc}"
    if FREE_STREAM_PROXIES:
        return FREE_STREAM_PROXIES[0].format(url=enc)
    return url


def apply_proxy_to_channels(channels):
    if not (CLOUDFLARE_WORKER_URL or PROXY_URL or FREE_STREAM_PROXIES):
        logger.info("No proxy configured - streams are used as-is.")
        return channels
    n = 0
    for ch in channels:
        url = ch.get("stream_url", "")
        if url and is_geo_blocked(url):
            ch["stream_url"] = wrap_with_proxy(url)
            n += 1
    logger.info(f"Proxy applied to {n} channels")
    return channels


def generate_streamlink_script(channels=None, output_path="scripts/play_channel.sh"):
    script = '''#!/bin/bash
# Play a stream with Streamlink + VLC, optionally via SOCKS5 proxy (SOCKS_PROXY=user:pass@host:port)
URL="$1"; QUALITY="${2:-best}"; VLC_CMD="${VLC:-vlc}"
[ -z "$URL" ] && { echo "Usage: $0 <url> [quality]"; exit 1; }
if [ -n "$SOCKS_PROXY" ]; then
  streamlink --http-proxy "socks5://$SOCKS_PROXY" --player "$VLC_CMD" "$URL" "$QUALITY"
else
  streamlink --player "$VLC_CMD" "$URL" "$QUALITY"
fi
'''
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(script)
    os.chmod(output_path, 0o755)


def generate_cloudflare_worker():
    js = r"""// Cloudflare Worker - HLS stream proxy (personal use). Restrict it to your own use.
export default {
  async fetch(request) {
    const url = new URL(request.url);
    const target = url.searchParams.get('url');
    const cors = { 'Access-Control-Allow-Origin': '*' };
    if (!target) return new Response('Usage: ?url=<encoded stream url>', { status: 400 });
    if (request.method === 'OPTIONS') return new Response(null, { headers: cors });
    try {
      const origin = new URL(target).origin;
      const upstream = await fetch(target, {
        headers: { 'User-Agent': 'Mozilla/5.0', 'Referer': origin + '/', 'Origin': origin },
      });
      const ctype = upstream.headers.get('Content-Type') || '';
      if (ctype.includes('mpegurl') || target.split('?')[0].endsWith('.m3u8')) {
        const base = target.substring(0, target.lastIndexOf('/') + 1);
        const text = (await upstream.text()).split('\n').map(line => {
          const l = line.trim();
          if (!l || l.startsWith('#')) return line;
          const abs = l.startsWith('http') ? l : new URL(l, base).href;
          return `${url.origin}/?url=${encodeURIComponent(abs)}`;
        }).join('\n');
        return new Response(text, { status: upstream.status, headers: {
          ...cors, 'Content-Type': 'application/vnd.apple.mpegurl', 'Cache-Control': 'no-cache' } });
      }
      return new Response(upstream.body, { status: upstream.status, headers: {
        ...cors, 'Content-Type': ctype || 'video/mp2t', 'Cache-Control': 'no-cache' } });
    } catch (e) {
      return new Response('Error: ' + e.message, { status: 500, headers: cors });
    }
  },
};
"""
    os.makedirs("docs", exist_ok=True)
    with open("docs/cloudflare_worker.js", "w") as f:
        f.write(js)
    return js
