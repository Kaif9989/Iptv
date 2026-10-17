#!/bin/bash
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
    streamlink \
        --socks-proxy "socks5://$PROXY" \
        --player "$VLC_CMD" \
        "$CHANNEL_URL" \
        "$QUALITY"
else
    streamlink \
        --player "$VLC_CMD" \
        "$CHANNEL_URL" \
        "$QUALITY"
fi
