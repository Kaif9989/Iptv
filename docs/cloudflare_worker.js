// Cloudflare Worker - HLS stream proxy (personal use). Restrict it to your own use.
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
