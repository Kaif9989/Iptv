#!/usr/bin/env python3
"""
Stream health checker. A stream counts as WORKING only if a real media segment can be
downloaded (master playlist -> media playlist -> first segment), not just the .m3u8 file.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _first_uri(text):
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return None


def _segment_ok(url, timeout):
    with requests.get(url, headers=UA, timeout=timeout, stream=True) as r:
        if r.status_code not in (200, 206):
            return False
        ctype = r.headers.get("Content-Type", "").lower()
        chunk = next(r.iter_content(chunk_size=1024), b"")
        return bool(chunk) and "text/html" not in ctype and b"<html" not in chunk[:200].lower()


def _get_text(url, timeout):
    r = requests.get(url, headers=UA, timeout=timeout, allow_redirects=True)
    if r.status_code != 200:
        return None, r.url
    return r.text[:300_000], r.url


def check_stream(url, timeout=10):
    try:
        text, final = _get_text(url, timeout)
        if text is None:
            return False
        if not text.lstrip().startswith("#EXTM3U"):
            # not a playlist: accept only if it is a direct video stream
            with requests.get(url, headers=UA, timeout=timeout, stream=True) as r:
                ct = r.headers.get("Content-Type", "").lower()
                return r.status_code == 200 and (ct.startswith("video/") or "mp2t" in ct)

        if "#EXT-X-STREAM-INF" in text:                  # master playlist -> go one level down
            variant = _first_uri(text)
            if not variant:
                return False
            final = urljoin(final, variant)
            text, final = _get_text(final, timeout)
            if text is None or not text.lstrip().startswith("#EXTM3U"):
                return False

        if "#EXT-X-ENDLIST" in text:                     # VOD, not a live channel
            return False
        seg = _first_uri(text)
        if not seg:
            return False
        return _segment_ok(urljoin(final, seg), timeout)
    except Exception:
        return False


def filter_working(channels, workers=20, timeout=10):
    logger.info(f"Checking {len(channels)} streams (a few minutes)...")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(lambda c: check_stream(c["stream_url"], timeout), channels))
    alive = []
    for ch, ok in zip(channels, results):
        ch["is_online"] = ok
        if ok:
            alive.append(ch)
    logger.info(f"{len(alive)}/{len(channels)} streams are working")
    return alive


# ─── Stability check: is the stream still LIVE after a while? ────────────────
import re
import time


def _media_playlist(url, timeout):
    text, final = _get_text(url, timeout)
    if text is None or not text.lstrip().startswith("#EXTM3U"):
        return None
    if "#EXT-X-STREAM-INF" in text:
        variant = _first_uri(text)
        if not variant:
            return None
        text, final = _get_text(urljoin(final, variant), timeout)
        if text is None or not text.lstrip().startswith("#EXTM3U"):
            return None
    return text, final


def _last_segment(text, final):
    uris = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#")]
    return urljoin(final, uris[-1]) if uris else None


def _media_seq(text):
    m = re.search(r"#EXT-X-MEDIA-SEQUENCE:(\d+)", text)
    return int(m.group(1)) if m else None


def check_stable(url, wait=70, timeout=10):
    """Fetch the playlist, wait, fetch again: it must have advanced and new video must download."""
    try:
        a = _media_playlist(url, timeout)
        if not a:
            return False
        time.sleep(wait)
        b = _media_playlist(url, timeout)
        if not b:
            return False
        sa, sb = _media_seq(a[0]), _media_seq(b[0])
        la, lb = _last_segment(*a), _last_segment(*b)
        advanced = (sa is not None and sb is not None and sb > sa) or (la != lb)
        return bool(advanced and lb and _segment_ok(lb, timeout))
    except Exception:
        return False


def filter_stable(channels, wait=70, workers=60, timeout=10):
    logger.info(f"Stability check on {len(channels)} streams (~{wait}s per batch of {workers})...")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(lambda c: check_stable(c["stream_url"], wait, timeout), channels))
    stable = [c for c, ok in zip(channels, results) if ok]
    logger.info(f"{len(stable)}/{len(channels)} streams are still live after {wait}s")
    return stable
