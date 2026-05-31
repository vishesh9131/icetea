/** Shared reverse-proxy to the real FastAPI host (Render/Railway/etc). */
export async function proxyToBackend(request) {
  const upstream = (process.env.BACKEND_URL || '').trim().replace(/\/$/, '')
  if (!upstream) {
    return new Response(
      JSON.stringify({
        error: 'BACKEND_URL not configured',
        hint: 'Deploy backend (see render.yaml) and set BACKEND_URL in Netlify env, e.g. https://icetea-api.onrender.com',
      }),
      { status: 503, headers: { 'content-type': 'application/json' } },
    )
  }

  const url = new URL(request.url)
  const target = `${upstream}${url.pathname}${url.search}`

  const headers = new Headers(request.headers)
  headers.delete('host')

  /** @type {RequestInit} */
  const init = { method: request.method, headers }

  if (request.method !== 'GET' && request.method !== 'HEAD') {
    init.body = request.body
    // @ts-expect-error required for streaming POST bodies (SSE chat)
    init.duplex = 'half'
  }

  const resp = await fetch(target, init)
  return new Response(resp.body, {
    status: resp.status,
    statusText: resp.statusText,
    headers: resp.headers,
  })
}
