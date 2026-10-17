// Cloudflare Worker - IPTV Stream Proxy
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
      text = text.replace(/^(?!#)([^\n]+\.ts[^\n]*)/gm, (match) => {
        if (match.startsWith('http')) {
          return `${url.origin}/?url=${encodeURIComponent(match)}`
        } else {
          return `${url.origin}/?url=${encodeURIComponent(baseUrl + match)}`
        }
      })
      
      // Also rewrite sub-playlist URLs
      text = text.replace(/^(?!#)([^\n]+\.m3u8[^\n]*)/gm, (match) => {
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
