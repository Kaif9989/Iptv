# 🌐 Geo-Blocked Channel Bypass Guide

This guide explains how to watch India IPTV channels that are geo-restricted (blocked outside India or only available in India).

---

## Option 1: Cloudflare Worker (FREE — Recommended)

Deploy a free Cloudflare Worker that proxies stream requests from India's region.

### Setup Steps

1. **Create a free Cloudflare account** at https://cloudflare.com

2. **Deploy the Worker:**
   - Go to Workers & Pages → Create Application → Create Worker
   - Replace the default code with the contents of `cloudflare_worker.js` in this repo
   - Click "Save and Deploy"
   - Copy your worker URL (e.g., `https://iptv-proxy.YOUR-NAME.workers.dev`)

3. **Add to GitHub Secrets:**
   - In your repo: Settings → Secrets → Actions → New secret
   - Name: `CLOUDFLARE_WORKER_URL`
   - Value: `https://iptv-proxy.YOUR-NAME.workers.dev`

4. **Re-run the workflow** — geo-blocked URLs will now be automatically proxied.

> ✅ Free tier: 100,000 requests/day — enough for personal IPTV use.

---

## Option 2: Personal VPS Proxy

If you have a VPS with an Indian IP address:

### Install 3proxy (lightweight)

```bash
apt install 3proxy
# /etc/3proxy/3proxy.cfg:
# socks -p1080
# proxy -p3128
systemctl start 3proxy
```

### Set in GitHub Secrets:
- `PROXY_URL` = `socks5://user:pass@your-vps-ip:1080`

---

## Option 3: Streamlink + VPN (Play Locally)

Use the included `scripts/play_channel.sh` with a SOCKS5 proxy:

```bash
# Install dependencies
pip install streamlink
apt install vlc

# Set your proxy
export SOCKS_PROXY="user:pass@your-proxy:1080"

# Play a channel
./scripts/play_channel.sh "https://stream-url.m3u8" best
```

---

## Option 4: WireGuard VPN on Your Router

For the cleanest solution — all devices on your network automatically bypass geo-blocks:

1. Set up a WireGuard server on a VPS with Indian IP
2. Configure your home router as a WireGuard client
3. All IPTV traffic appears to come from India

### Quick WireGuard Server Setup (on Indian VPS):

```bash
# Install WireGuard
apt install wireguard

# Generate keys
wg genkey | tee server_private.key | wg pubkey > server_public.key

# Create config (/etc/wireguard/wg0.conf)
[Interface]
Address = 10.0.0.1/24
PrivateKey = <server_private_key>
ListenPort = 51820
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE

[Peer]
PublicKey = <client_public_key>
AllowedIPs = 10.0.0.2/32

# Start
wg-quick up wg0
systemctl enable wg-quick@wg0
```

---

## Option 5: Free Public Proxies (Not Recommended)

Free proxies are unreliable and may drop connections. Only use as a last resort:

```python
# In geobypass.py, add to FREE_STREAM_PROXIES:
FREE_STREAM_PROXIES = [
    "https://your-free-proxy.com/proxy?url={url}"
]
```

---

## Checking if a Channel is Geo-Blocked

The scraper automatically detects and flags known geo-blocked domains:
- `hotstar.com` / `jiohotstar.com`
- `jiocinema.com`
- `sonyliv.com`
- `zee5.com`
- `voot.com`

These are automatically routed through your configured proxy.

---

## Recommended Indian VPS Providers

| Provider | Monthly Cost | Notes |
|----------|-------------|-------|
| Hetzner (Mumbai) | ~$5 | Great performance |
| DigitalOcean (Bangalore) | ~$6 | Easy setup |
| Vultr (Mumbai) | ~$6 | Good speeds |
| AWS Lightsail (Mumbai) | ~$3.5 | AWS reliability |

*For pure streaming proxy use, the smallest/cheapest plan is sufficient.*
