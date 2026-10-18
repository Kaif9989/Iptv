#!/bin/bash
# Play a stream with Streamlink + VLC, optionally via SOCKS5 proxy (SOCKS_PROXY=user:pass@host:port)
URL="$1"; QUALITY="${2:-best}"; VLC_CMD="${VLC:-vlc}"
[ -z "$URL" ] && { echo "Usage: $0 <url> [quality]"; exit 1; }
if [ -n "$SOCKS_PROXY" ]; then
  streamlink --http-proxy "socks5://$SOCKS_PROXY" --player "$VLC_CMD" "$URL" "$QUALITY"
else
  streamlink --player "$VLC_CMD" "$URL" "$QUALITY"
fi
