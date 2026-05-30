import type { ChatRequest, SseEvent } from './types'

// Browsers' EventSource only does GET, but our backend takes POST with a
// JSON body, so we hand-roll the SSE parser on top of fetch's ReadableStream.
// The wire format from src/api/sse.py is:
//   event: <name>
//   data: <line>
//   data: <line>     (optional, may repeat for pretty JSON)
//   <blank line>     (frame terminator)
//
// We buffer until we see a blank line, then assemble the frame.

export type StreamCallbacks = {
  onEvent: (ev: SseEvent) => void
  onOpen?: () => void
  onClose?: (info: { aborted: boolean; error?: Error }) => void
}

export type StreamHandle = {
  abort: () => void
  promise: Promise<void>
}

const DEFAULT_BASE = 'http://127.0.0.1:8000'

function backendBase(): string {
  // Allow VITE_BACKEND_BASE override (e.g. behind a tunnel); otherwise local.
  // import.meta.env exists at build time under Vite.
  const fromEnv = (import.meta as any)?.env?.VITE_BACKEND_BASE
  return (fromEnv && typeof fromEnv === 'string' && fromEnv.trim()) || DEFAULT_BASE
}

export function streamChat(
  req: ChatRequest,
  cb: StreamCallbacks,
): StreamHandle {
  const ctl = new AbortController()
  const url = `${backendBase()}/v1/chat`

  const promise = (async () => {
    try {
      const resp = await fetch(url, {
        method: 'POST',
        signal: ctl.signal,
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
        },
        body: JSON.stringify(req),
      })
      if (!resp.ok || !resp.body) {
        const text = await safeText(resp)
        throw new Error(`backend ${resp.status}: ${text || resp.statusText}`)
      }
      cb.onOpen?.()
      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        // SSE frames are separated by \n\n. We may receive partial frames in
        // a chunk, so we split, keep the trailing slice as the new buffer,
        // and emit anything complete.
        let idx: number
        while ((idx = buf.indexOf('\n\n')) !== -1) {
          const frame = buf.slice(0, idx)
          buf = buf.slice(idx + 2)
          const ev = parseFrame(frame)
          if (ev) cb.onEvent(ev)
        }
      }
      cb.onClose?.({ aborted: false })
    } catch (err) {
      const aborted = ctl.signal.aborted
      cb.onClose?.({ aborted, error: aborted ? undefined : (err as Error) })
    }
  })()

  return { abort: () => ctl.abort(), promise }
}

async function safeText(r: Response): Promise<string> {
  try { return await r.text() } catch { return '' }
}

function parseFrame(frame: string): SseEvent | null {
  // A frame is several lines: `event: <name>` and one or more `data: ...`.
  // Comments (lines starting with `:`) and `id:`/`retry:` lines we ignore.
  let eventName = 'message'
  const dataLines: string[] = []
  for (const rawLine of frame.split('\n')) {
    const line = rawLine.replace(/\r$/, '')
    if (!line) continue
    if (line.startsWith(':')) continue
    const colon = line.indexOf(':')
    if (colon < 0) continue
    const field = line.slice(0, colon).trim()
    let value = line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') eventName = value
    else if (field === 'data') dataLines.push(value)
  }
  if (dataLines.length === 0) return null
  const raw = dataLines.join('\n')
  let payload: any
  try {
    payload = JSON.parse(raw)
  } catch {
    payload = { _raw: raw }
  }
  switch (eventName) {
    case 'token':
      return { kind: 'token', delta: typeof payload?.delta === 'string' ? payload.delta : '' }
    case 'thinking':
      return { kind: 'thinking', delta: typeof payload?.delta === 'string' ? payload.delta : '' }
    case 'structured':
      return { kind: 'structured', payload }
    case 'meta':
      return { kind: 'meta', payload }
    case 'error':
      return { kind: 'error', payload }
    case 'done':
      return { kind: 'done', payload }
    default:
      return { kind: 'other', name: eventName, payload }
  }
}

export type HealthInfo = {
  status: string
  llm_provider?: string
  model?: string
  app_env?: string
}

export async function pingHealth(): Promise<HealthInfo | null> {
  try {
    const r = await fetch(`${backendBase()}/healthz`, { method: 'GET' })
    if (!r.ok) return null
    return (await r.json()) as HealthInfo
  } catch {
    return null
  }
}

export type ServiceMeta = {
  service: string
  version: string
  app_env: string
  llm_provider: string
  model: string
  request_timeout_s: number
  multiagent_rounds: number
}

export async function fetchMeta(): Promise<ServiceMeta | null> {
  try {
    const r = await fetch(`${backendBase()}/v1/meta`, { method: 'GET' })
    if (!r.ok) return null
    return (await r.json()) as ServiceMeta
  } catch {
    return null
  }
}

// ---- LLM provider switch (used by onboarding + activity bar) -------------

export type LlmProviderId = 'vllm' | 'openai' | 'claude'

export type ProviderInfo = {
  id: LlmProviderId
  label: string
  model: string
  base_url: string
  configured: boolean
  note: string
}

export type ProviderList = {
  active: LlmProviderId
  providers: ProviderInfo[]
}

export async function fetchProviders(): Promise<ProviderList | null> {
  try {
    const r = await fetch(`${backendBase()}/v1/runtime/llm-providers`)
    if (!r.ok) return null
    return (await r.json()) as ProviderList
  } catch {
    return null
  }
}

export async function setLlmProvider(
  provider: LlmProviderId,
): Promise<{ ok: boolean; provider?: LlmProviderId; model?: string; error?: string }> {
  try {
    const r = await fetch(`${backendBase()}/v1/runtime/llm-provider`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider }),
    })
    const data = await r.json().catch(() => ({}))
    if (!r.ok) return { ok: false, error: data?.detail || `HTTP ${r.status}` }
    return { ok: true, provider: data.provider, model: data.model }
  } catch (e: unknown) {
    return { ok: false, error: (e as Error)?.message || 'network error' }
  }
}

export type TapeItem = {
  sym: string
  yf: string
  last: number | null
  change_pct: number | null
  unit: string | null
  error: string | null
}
export type TapePayload = { as_of: number; stale: boolean; items: TapeItem[] }

export async function fetchTape(): Promise<TapePayload | null> {
  try {
    const r = await fetch(`${backendBase()}/v1/market/tape`, { method: 'GET' })
    if (!r.ok) return null
    return (await r.json()) as TapePayload
  } catch {
    return null
  }
}

// ---- news ----------------------------------------------------------

export type NewsItem = {
  id: string
  title: string
  summary: string | null
  url: string | null
  source: string | null
  image: string | null
  published_at: string | null
  published_ts: number | null
  tickers: string[]
}
export type NewsPayload = {
  as_of: number
  scope: 'market' | 'portfolio'
  tickers?: string[]
  items: NewsItem[]
}

export async function fetchMarketNews(): Promise<NewsPayload | null> {
  try {
    const r = await fetch(`${backendBase()}/v1/news/market`, { method: 'GET' })
    if (!r.ok) return null
    return (await r.json()) as NewsPayload
  } catch { return null }
}

export async function fetchPortfolioNews(tickers: string[]): Promise<NewsPayload | null> {
  const qs = new URLSearchParams({ tickers: tickers.join(',') }).toString()
  try {
    const r = await fetch(`${backendBase()}/v1/news/portfolio?${qs}`, { method: 'GET' })
    if (!r.ok) return null
    return (await r.json()) as NewsPayload
  } catch { return null }
}

// ---- in-app article reader ---------------------------------------

export type ArticlePayload = {
  ok: boolean
  url: string
  text: string
  note: string | null
  http_status: number | null
  fetched_at: number
}

export async function fetchArticle(url: string): Promise<ArticlePayload | null> {
  const qs = new URLSearchParams({ url }).toString()
  try {
    const r = await fetch(`${backendBase()}/v1/reader/article?${qs}`, { method: 'GET' })
    if (!r.ok) return null
    return (await r.json()) as ArticlePayload
  } catch { return null }
}

// ---- agents (builder UI) ------------------------------------------

export type BuiltinAgent = {
  id: string
  label: string
  kind: 'builtin'
  implemented: boolean
}
export type CustomAgent = {
  id: string
  label: string
  description: string
  system_prompt: string
  tools: string[]
  temperature: number
  max_tokens: number
}
export type AgentsList = { builtin: BuiltinAgent[]; custom: CustomAgent[] }

export type ToolDescriptor = {
  tool_id: string
  label: string
  description: string
  inputs: string[]
  group: string
}

export async function fetchAgents(): Promise<AgentsList | null> {
  try {
    const r = await fetch(`${backendBase()}/v1/agents`, { method: 'GET' })
    if (!r.ok) return null
    return (await r.json()) as AgentsList
  } catch { return null }
}

export async function fetchToolCatalog(): Promise<ToolDescriptor[]> {
  try {
    const r = await fetch(`${backendBase()}/v1/tools/catalog`, { method: 'GET' })
    if (!r.ok) return []
    const d = await r.json()
    return Array.isArray(d?.tools) ? (d.tools as ToolDescriptor[]) : []
  } catch { return [] }
}

export async function upsertAgent(payload: CustomAgent): Promise<{ ok: boolean; error?: string }> {
  try {
    const r = await fetch(`${backendBase()}/v1/agents`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!r.ok) {
      const err = await r.json().catch(() => ({}))
      return { ok: false, error: err?.detail || `HTTP ${r.status}` }
    }
    return { ok: true }
  } catch (e) { return { ok: false, error: (e as Error).message } }
}

export async function deleteAgent(id: string): Promise<{ ok: boolean; error?: string }> {
  try {
    const r = await fetch(`${backendBase()}/v1/agents/${encodeURIComponent(id)}`, { method: 'DELETE' })
    if (!r.ok) {
      const err = await r.json().catch(() => ({}))
      return { ok: false, error: err?.detail || `HTTP ${r.status}` }
    }
    return { ok: true }
  } catch (e) { return { ok: false, error: (e as Error).message } }
}
