import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ImperativePanelHandle } from 'react-resizable-panels'
import { AgentBuilder } from './components/AgentBuilder'
import { AgentTracePanel } from './components/AgentTracePanel'
import { ChatPanel } from './components/ChatPanel'
import { CommandBar, type CommandAction } from './components/CommandBar'
import { Header } from './components/Header'
import { NewsPanel } from './components/NewsPanel'
import { PortfolioPanel } from './components/PortfolioPanel'
import { ProfileSummary } from './components/ProfileSummary'
import { ReaderPanel } from './components/ReaderPanel'
import { StatusBar } from './components/StatusBar'
import { Ticker } from './components/Ticker'
import { Dock, collapsedSet } from './dock/Dock'
import { PanelFrame } from './dock/PanelFrame'
import { TILE_IDS, type TileId } from './dock/layout'
import { useDockLayout } from './dock/useDockLayout'
import { OnboardingFlow, type OnboardingResult } from './onboarding/OnboardingFlow'
import { defaultProfile, getProfiles, loadProfiles, type Profile } from './profiles'
import { pingHealth, streamChat, type HealthInfo, type NewsItem, type StreamHandle } from './sseClient'
import type { ChatMessage, TraceEntry, UserContext } from './types'
import { useTheme } from './useTheme'

const SESSION_PREFIX = 'term'

// Bumped to v2 if the onboarding shape changes - this is the localStorage
// key we check to decide whether to show the first-run overlay.
const ONBOARDING_KEY = 'icetea.onboarded.v1'

function readOnboardingFlag(): boolean {
  try {
    return window.localStorage.getItem(ONBOARDING_KEY) === '1'
  } catch {
    return false
  }
}

function writeOnboardingFlag(done: boolean) {
  try {
    if (done) window.localStorage.setItem(ONBOARDING_KEY, '1')
    else window.localStorage.removeItem(ONBOARDING_KEY)
  } catch {
    // ignore - private browsing etc. we just re-show the flow next boot.
  }
}

function newSessionId(): string {
  // session ids must be stable across a thread but cheap to regenerate when
  // the operator wants a clean slate. Backend session store keys off this.
  const rand = Math.random().toString(36).slice(2, 9)
  return `${SESSION_PREFIX}-${Date.now().toString(36)}-${rand}`
}

function makeId(): string {
  return Math.random().toString(36).slice(2, 11)
}

export function App() {
  // Profile list is loaded async from /profiles.json. Until it resolves we
  // hold the placeholder profile from profiles.ts. Once loaded we hop onto
  // the JSON-declared default so the UI doesnt sit on "LOADING..." forever.
  const [profiles, setProfiles] = useState<Profile[]>(() => getProfiles())
  const initialProfile = useMemo(defaultProfile, [])
  const [profileId, setProfileId] = useState<string>(initialProfile.id)
  const [ctx, setCtx] = useState<UserContext>(initialProfile.ctx)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [trace, setTrace] = useState<TraceEntry[]>([])
  const [sessionId, setSessionId] = useState<string>(newSessionId())
  const [collaborative, setCollab] = useState(false)
  const [busy, setBusy] = useState(false)
  const [online, setOnline] = useState(false)
  const [health, setHealth] = useState<HealthInfo | null>(null)
  const [lastAgent, setLastAgent] = useState<string | null>(null)
  const [lastLatency, setLastLatency] = useState<number | null>(null)
  const [blockedCount, setBlockedCount] = useState(0)
  const streamRef = useRef<StreamHandle | null>(null)
  const [theme, setTheme, cycleTheme] = useTheme()
  const [builderOpen, setBuilderOpen] = useState(false)
  // article currently open in the in-app READER dock tile (null = placeholder)
  const [readerArticle, setReaderArticle] = useState<NewsItem | null>(null)

  // First-run onboarding gate. `done` flips true after the operator finishes
  // the flow (or skips with ESC). `profilesReady` blocks the splash from
  // rendering bucket cards before profiles.json has resolved - otherwise
  // we'd show one disabled "LOADING" tile and look broken.
  const [onboardingDone, setOnboardingDone] = useState<boolean>(() => readOnboardingFlag())
  const [profilesReady, setProfilesReady] = useState(false)

  const handleOnboardingComplete = useCallback((res: OnboardingResult) => {
    // Apply the chosen profile, then stamp the operator name into the
    // active user_context so PROFILE/CHAT both pick it up immediately.
    const list = getProfiles()
    const picked = list.find((p) => p.id === res.profileId) || list[0]
    if (picked) {
      setProfileId(picked.id)
      // setProfileId runs a useEffect that resets ctx from the profile - we
      // need to overlay the operator name after that lands. simplest is to
      // do both in this tick: ctx is set here, the effect re-set runs next
      // and will respect the name we just placed because it reads `profiles`
      // (which still has the original `name`) - so we ALSO patch the live
      // ctx state right away and a second time after the effect runs.
      const ctxWithName: UserContext = {
        ...picked.ctx,
        name: res.name || picked.ctx.name || null,
      }
      setCtx(ctxWithName)
    }
    writeOnboardingFlag(true)
    setOnboardingDone(true)
  }, [])

  // ---- dock layout (resizable / draggable / collapsible tiles) -------
  const dock = useDockLayout()
  const [focusedTile, setFocusedTile] = useState<TileId | null>(null)

  // wired here so it can use dock + setFocusedTile after both exist.
  const openInReader = useCallback((it: NewsItem) => {
    setReaderArticle(it)
    setFocusedTile('reader')
    dock.setCollapsed('reader', false)
  }, [dock])
  const tileHandles = useRef<Partial<Record<TileId, ImperativePanelHandle | null>>>({})
  const collapsed = useMemo(() => collapsedSet(dock.layout), [dock.layout])

  const registerHandle = useCallback(
    (tile: TileId, h: ImperativePanelHandle | null) => {
      tileHandles.current[tile] = h
    },
    [],
  )

  const focusTile = useCallback((t: TileId) => {
    setFocusedTile(t)
    // make sure a collapsed tile expands when focused via keyboard
    if (collapsed.has(t)) dock.setCollapsed(t, false)
  }, [collapsed, dock])

  // Cmd/Ctrl + Shift + Arrow grows/shrinks the focused tile.
  // Step is 5% of the panel group; clamped by react-resizable-panels' minSize.
  const nudgeFocused = useCallback((delta: number) => {
    const t = focusedTile
    if (!t) return
    const h = tileHandles.current[t]
    if (!h) return
    const cur = h.getSize()
    const next = Math.max(4, Math.min(96, cur + delta))
    h.resize(next)
  }, [focusedTile])

  // ---- global keyboard router for dock ops + theme cycle -------------
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'F12') {
        e.preventDefault()
        cycleTheme()
        return
      }
      const meta = e.metaKey || e.ctrlKey
      if (!meta) return

      // Cmd+B - open the agent builder overlay
      if (!e.shiftKey && (e.key === 'b' || e.key === 'B')) {
        e.preventDefault()
        setBuilderOpen((v) => !v)
        return
      }

      // Cmd+Shift+O - replay the onboarding flow. Clears the persist flag
      // and forces the splash back. Handy for first-time demos.
      if (e.shiftKey && (e.key === 'O' || e.key === 'o')) {
        e.preventDefault()
        writeOnboardingFlag(false)
        setOnboardingDone(false)
        return
      }

      // Cmd+Shift+R — reset dock layout
      if (e.shiftKey && (e.key === 'R' || e.key === 'r')) {
        e.preventDefault()
        dock.reset()
        return
      }

      // Cmd+M — collapse / expand focused tile
      if (!e.shiftKey && (e.key === 'm' || e.key === 'M')) {
        if (!focusedTile) return
        e.preventDefault()
        dock.toggleCollapsed(focusedTile)
        return
      }

      // Cmd+Shift+Arrow — resize focused tile
      if (e.shiftKey) {
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
          e.preventDefault()
          nudgeFocused(+5)
          return
        }
        if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
          e.preventDefault()
          nudgeFocused(-5)
          return
        }
      }

      // Cmd+1..4 focus, Cmd+Shift+1..4 swap focused tile with target
      const n = Number.parseInt(e.key, 10)
      if (!Number.isNaN(n) && n >= 1 && n <= TILE_IDS.length) {
        const target = TILE_IDS[n - 1]
        if (e.shiftKey) {
          if (focusedTile && focusedTile !== target) {
            e.preventDefault()
            dock.swap(focusedTile, target)
            // focus follows the moved tile to its new slot
            setFocusedTile(focusedTile)
          }
        } else {
          e.preventDefault()
          focusTile(target)
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [cycleTheme, dock, focusTile, focusedTile, nudgeFocused])

  // ---- backend health probe ------------------------------------------
  useEffect(() => {
    let stopped = false
    const probe = async () => {
      const h = await pingHealth()
      if (stopped) return
      setOnline(!!h)
      if (h) setHealth(h)
    }
    probe()
    const i = setInterval(probe, 10_000)
    return () => { stopped = true; clearInterval(i) }
  }, [])

  // ---- one-shot profiles.json fetch on mount -------------------------
  useEffect(() => {
    let stopped = false
    loadProfiles().then((list) => {
      if (stopped) return
      setProfiles(list)
      // if we are still showing the placeholder, hop onto the real default
      const stillPlaceholder = list.find((p) => p.id === profileId) === undefined
      if (stillPlaceholder) {
        const def = defaultProfile()
        setProfileId(def.id)
        setCtx(def.ctx)
      }
      setProfilesReady(true)
    })
    return () => { stopped = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ---- profile switch resets the session so memory carryover doesnt cross
  useEffect(() => {
    const p = profiles.find((x) => x.id === profileId)
    if (!p) return
    setCtx(p.ctx)
    setSessionId(newSessionId())
    setMessages([])
    setTrace([])
    setLastAgent(null)
    setLastLatency(null)
  }, [profileId, profiles])

  // ---- core send -----------------------------------------------------
  const send = useCallback((text: string, opts?: { agent_override?: string | null }) => {
    if (!text.trim()) return
    if (streamRef.current) {
      // already streaming — cancel and start fresh
      streamRef.current.abort()
      streamRef.current = null
    }

    const override = opts?.agent_override || null

    const userMsg: ChatMessage = {
      id: makeId(), role: 'user', text, ts: Date.now(),
    }
    const botId = makeId()
    const botMsg: ChatMessage = {
      id: botId, role: 'assistant', text: '', ts: Date.now(),
      agent: override, collaborative, streaming: true,
    }
    setMessages((prev) => [...prev, userMsg, botMsg])

    const start = Date.now()
    setBusy(true)

    const pushTrace = (e: Omit<TraceEntry, 'id' | 'ts'>) =>
      setTrace((prev) => trim([...prev, { ...e, id: makeId(), ts: Date.now() }]))

    pushTrace({ kind: 'session', label: 'SEND', body: shortenForTrace(text) + (override ? ` (override=${override})` : '') })

    const handle = streamChat(
      { query: text, session_id: sessionId, user_context: ctx, collaborative, agent_override: override },
      {
        onOpen: () => pushTrace({ kind: 'meta', label: 'OPEN', body: '/v1/chat' }),
        onEvent: (ev) => {
          if (ev.kind === 'token') {
            setMessages((prev) => prev.map((m) => m.id === botId
              ? { ...m, text: m.text + ev.delta, progress: null }
              : m,
            ))
            // we do NOT trace every token — too noisy. Just count rough chunks.
            return
          }
          if (ev.kind === 'meta') {
            const pl = ev.payload as any
            const stage = String(pl.stage || '')
            const agent = pl.agent
            // Surface collaborative supervisor progress directly in the bubble
            // so the operator sees what is running, not just a blank waiting
            // cursor while 6-10 agents take their turn.
            if (stage === 'agent_discussion' || stage === 'planner' || stage === 'synthesis') {
              setMessages((prev) => prev.map((m) => m.id === botId
                ? { ...m, progress: { stage, round: pl.round, agent: agent ? String(agent) : undefined } }
                : m))
            }
            // Backend event shape (src/api/sse.py + pipeline):
            //   { stage: "safety", blocked: bool, category?, latency_ms? }
            // We collapse the "blocked" branch here so the UI status bar
            // and chat bubble both reflect it without waiting for done.
            const safetyBlocked = stage === 'safety' && pl.blocked === true
            const cat = pl.category
            if (safetyBlocked) {
              setBlockedCount((c) => c + 1)
              setLastAgent('safety_guard')
              setMessages((prev) => prev.map((m) => m.id === botId
                ? { ...m, agent: 'safety_guard', blocked: true, blockCategory: cat || undefined }
                : m))
              pushTrace({ kind: 'guard', label: 'BLOCKED', body: kvSummary(pl) })
              return
            }
            if (stage === 'classified' && agent) {
              setLastAgent(String(agent))
              setMessages((prev) => prev.map((m) => m.id === botId
                ? { ...m, agent: String(agent) } : m))
              pushTrace({ kind: 'classif', label: 'CLASSIF', body: kvSummary(pl) })
              return
            }
            pushTrace({ kind: 'meta', label: stage ? stage.toUpperCase() : 'META', body: kvSummary(pl) })
            return
          }
          if (ev.kind === 'structured') {
            const agent = (ev.payload as any).agent || lastAgent
            setMessages((prev) => prev.map((m) => m.id === botId
              ? { ...m, structured: ev.payload, agent: agent ? String(agent) : m.agent }
              : m))
            pushTrace({ kind: 'structured', label: 'STRUCT', body: kvSummary(ev.payload, ['agent', 'intent', 'mode', 'implemented']) })
            return
          }
          if (ev.kind === 'error') {
            const code = (ev.payload as any).code || 'error'
            const msg = (ev.payload as any).message || JSON.stringify(ev.payload)
            // Most common error in COLLAB mode is the pipeline timeout. Replace
            // the bare "[timeout] pipeline_timeout" with something actionable.
            let friendly = `[${code}] ${msg}`
            if (String(code).includes('timeout') || String(msg).includes('timeout')) {
              friendly =
                `[${code}] the pipeline hit its wall-clock cap before the supervisor finished.\n` +
                (collaborative
                  ? `   COLLAB is ON, which runs 6-10 agents in series. Try:\n` +
                    `   - press F10 to turn COLLAB off and ask the same question (single agent)\n` +
                    `   - or split the question (e.g. ask the strategy and risk sides separately)`
                  : `   try a narrower question, or check the backend uvicorn output for a slow LLM round`)
            }
            setMessages((prev) => prev.map((m) => m.id === botId
              ? { ...m, role: 'error', text: m.text + (m.text ? '\n' : '') + friendly, streaming: false, progress: null }
              : m))
            pushTrace({ kind: 'error', label: 'ERROR', body: `${code}: ${msg}` })
            return
          }
          if (ev.kind === 'done') {
            const latency = Date.now() - start
            setLastLatency(latency)
            setMessages((prev) => prev.map((m) => m.id === botId
              ? { ...m, streaming: false, latencyMs: latency, progress: null }
              : m))
            pushTrace({ kind: 'done', label: 'DONE', body: `${(latency/1000).toFixed(2)}s · ${kvSummary(ev.payload)}` })
            return
          }
          pushTrace({ kind: 'other', label: (ev as any).name || 'OTHER', body: kvSummary((ev as any).payload || {}) })
        },
        onClose: ({ aborted, error }) => {
          if (streamRef.current === handle) streamRef.current = null
          setBusy(false)
          if (aborted) {
            setMessages((prev) => prev.map((m) => m.id === botId
              ? { ...m, streaming: false, text: m.text + (m.text ? '\n' : '') + '[cancelled]' }
              : m))
            pushTrace({ kind: 'meta', label: 'ABORT', body: 'cancelled by operator' })
            return
          }
          if (error) {
            setMessages((prev) => prev.map((m) => m.id === botId
              ? { ...m, role: 'error', text: m.text + (m.text ? '\n' : '') + `[transport] ${error.message}`, streaming: false }
              : m))
            pushTrace({ kind: 'error', label: 'XPORT', body: error.message })
            return
          }
          // graceful close with no `done` event - mark stream finished
          setMessages((prev) => prev.map((m) => m.id === botId
            ? { ...m, streaming: false, latencyMs: m.latencyMs ?? (Date.now() - start) }
            : m))
        },
      },
    )
    streamRef.current = handle
  }, [collaborative, ctx, lastAgent, sessionId])

  // ---- command bar action router -------------------------------------
  const onAction = useCallback((a: CommandAction) => {
    if (a.kind === 'send') send(a.text)
    else if (a.kind === 'cancel') streamRef.current?.abort()
    else if (a.kind === 'clear') {
      setMessages([])
      setTrace([])
      setSessionId(newSessionId())
      setLastAgent(null)
      setLastLatency(null)
    }
    else if (a.kind === 'toggle-collab') setCollab((v) => !v)
    else if (a.kind === 'help') {
      setMessages((prev) => [...prev, {
        id: makeId(), role: 'system', ts: Date.now(),
        text:
`HELP — ICETEA TERMINAL

Function keys             Mac alias       Action
  F1   CHAT                Ctrl+1         "how is my portfolio doing?"        → portfolio_health
  F2   PORT                Ctrl+2         "show me my holdings"               → portfolio_query
  F3   RISK                Ctrl+3         "stress test ... market drops 30%"  → risk_assessment
  F4   MR                  Ctrl+4         "how is nvda doing this week?"      → market_research
  F5   STRAT               Ctrl+5         "should i sell half of nvda?"       → investment_strategy
  F6   DEBATE              Ctrl+6         "bull case AND bear case on MSFT"   → investment_debate
  F7   PLAN                Ctrl+7         "retirement at 60 ..."              → financial_planning
  F8   HELP                Ctrl+8         this screen
  F9   CLEAR               Ctrl+9         wipe transcript + new session id
  F10  COLLAB              Ctrl+0         toggle multi-agent collaborative mode
  F12                                     cycle terminal theme
  ESC                                     cancel the in-flight stream
  /                                       focus the command bar

  (on macOS the top-row F1..F10 keys default to brightness/volume; either flip
   System Settings -> Keyboard -> "Use F1, F2, etc. keys as standard function
   keys", or just use the Ctrl+digit aliases above.)

Dock layout (\u2318 = Ctrl on Windows/Linux)
  drag splitter      resize neighbouring panels
  drag panel header  drop onto another panel to swap them
  double-click hdr   collapse / expand that panel
  \u2318 1..6            focus panel  (1=CHAT 2=PORT 3=PROF 4=TRACE 5=NEWS 6=READER)
  \u2318 Shift 1..6      swap focused panel with the chosen one
  \u2318 Shift \u2190/\u2192/\u2191/\u2193  resize focused panel  (5% step)
  \u2318 M              collapse / expand focused panel
  \u2318 Shift R        reset layout to default
  \u2318 B              open the AGENT BUILDER overlay (build/edit custom agents)
  \u2318 Shift O        replay the first-run onboarding (splash, name, portfolio, tour)
  layout persists per-browser to localStorage[icetea.layout.v3]

News + reader
  click any headline    open the article inside the READER dock tile
  \u2318/Ctrl/Shift click  open the article in a new browser tab instead

Pipeline
  every send hits POST /v1/chat with the portfolio in the side panel.
  events arrive over SSE: token (streamed text), meta (stage transitions),
  structured (the agent's machine payload), error, done.`,
        agent: 'HELP',
      }])
    }
  }, [send])

  const renderers: Record<TileId, React.ReactNode> = useMemo(() => ({
    chat: (
      <PanelFrame
        tile="chat"
        focused={focusedTile === 'chat'}
        collapsed={collapsed.has('chat')}
        hint={<>&lt;F1&gt;</>}
        rightExtra={<span className="ph-stat">{messages.length} MSG</span>}
        onToggleCollapse={() => dock.toggleCollapsed('chat')}
        onFocus={() => setFocusedTile('chat')}
      >
        <ChatPanel messages={messages} streaming={busy} />
      </PanelFrame>
    ),
    portfolio: (
      <PanelFrame
        tile="portfolio"
        focused={focusedTile === 'portfolio'}
        collapsed={collapsed.has('portfolio')}
        hint={<>&lt;F2&gt;</>}
        rightExtra={<span className="ph-stat">{ctx.positions.length} POS</span>}
        onToggleCollapse={() => dock.toggleCollapsed('portfolio')}
        onFocus={() => setFocusedTile('portfolio')}
      >
        <PortfolioPanel
          ctx={ctx}
          setCtx={setCtx}
          profileId={profileId}
          onProfileChange={setProfileId}
          profiles={profiles}
        />
      </PanelFrame>
    ),
    profile: (
      <PanelFrame
        tile="profile"
        focused={focusedTile === 'profile'}
        collapsed={collapsed.has('profile')}
        rightExtra={<span className="ph-stat">{ctx.user_id}</span>}
        onToggleCollapse={() => dock.toggleCollapsed('profile')}
        onFocus={() => setFocusedTile('profile')}
      >
        <ProfileSummary ctx={ctx} />
      </PanelFrame>
    ),
    trace: (
      <PanelFrame
        tile="trace"
        focused={focusedTile === 'trace'}
        collapsed={collapsed.has('trace')}
        hint={<>&lt;F8&gt;</>}
        rightExtra={
          <>
            <span className="ph-stat">{trace.length} EV</span>
            <button
              className="dock-btn"
              onClick={(e) => { e.stopPropagation(); setTrace([]) }}
              title="CLEAR TRACE"
            >[CLR]</button>
          </>
        }
        onToggleCollapse={() => dock.toggleCollapsed('trace')}
        onFocus={() => setFocusedTile('trace')}
      >
        <AgentTracePanel entries={trace} />
      </PanelFrame>
    ),
    news: (
      <PanelFrame
        tile="news"
        focused={focusedTile === 'news'}
        collapsed={collapsed.has('news')}
        hint={<>live</>}
        rightExtra={<span className="ph-stat">YFINANCE</span>}
        onToggleCollapse={() => dock.toggleCollapsed('news')}
        onFocus={() => setFocusedTile('news')}
      >
        <NewsPanel ctx={ctx} onOpenArticle={openInReader} />
      </PanelFrame>
    ),
    reader: (
      <PanelFrame
        tile="reader"
        focused={focusedTile === 'reader'}
        collapsed={collapsed.has('reader')}
        hint={<>in-app</>}
        rightExtra={
          <>
            <span className="ph-stat">{readerArticle ? 'OPEN' : 'IDLE'}</span>
            {readerArticle && (
              <button
                className="dock-btn"
                onClick={(e) => { e.stopPropagation(); setReaderArticle(null) }}
                title="CLOSE ARTICLE"
              >[CLR]</button>
            )}
          </>
        }
        onToggleCollapse={() => dock.toggleCollapsed('reader')}
        onFocus={() => setFocusedTile('reader')}
      >
        <ReaderPanel article={readerArticle} />
      </PanelFrame>
    ),
  }), [busy, collapsed, ctx, dock, focusedTile, messages, openInReader, profileId, profiles, readerArticle, trace])

  // ---- first-run onboarding gate -------------------------------------
  // We block the dashboard render entirely until the operator finishes (or
  // skips) onboarding. That way the splash gets the whole viewport and the
  // dashboard never flashes underneath.
  if (!onboardingDone) {
    if (!profilesReady) {
      // brief gap between mount and profiles.json - show the splash gem
      // alone so the screen isn't blank. Auto-advances once profiles land.
      return (
        <div className="onb-overlay">
          <div className="onb-splash">
            <pre className="ice-art" aria-hidden="true">{'  loading...'}</pre>
          </div>
        </div>
      )
    }
    return (
      <OnboardingFlow profiles={profiles} onComplete={handleOnboardingComplete} />
    )
  }

  return (
    <div className="terminal">
      <Header
        sessionId={sessionId}
        model={health?.model}
        provider={health?.llm_provider}
        appEnv={health?.app_env}
        online={online}
      />
      <Ticker />
      <div className="terminal-body">
        <Dock
          layout={dock.layout}
          renderers={renderers}
          onSplitResize={dock.setSplitSizes}
          onTileSwap={dock.swap}
          focused={focusedTile}
          collapsed={collapsed}
          registerHandle={registerHandle}
        />
      </div>
      <CommandBar
        busy={busy}
        collaborative={collaborative}
        onAction={onAction}
        onOpenBuilder={() => setBuilderOpen(true)}
      />
      <StatusBar
        online={online}
        busy={busy}
        lastAgent={lastAgent}
        lastLatencyMs={lastLatency}
        blockedCount={blockedCount}
        collaborative={collaborative}
        sessionId={sessionId}
        theme={theme}
        onThemeChange={setTheme}
      />
      {builderOpen && (
        <AgentBuilder
          onClose={() => setBuilderOpen(false)}
          onRunAgent={(id, query) => send(query, { agent_override: id })}
        />
      )}
    </div>
  )
}

// ---- small formatting helpers (kept here to avoid yet another file) ----

function kvSummary(obj: Record<string, unknown>, prefer?: string[]): string {
  if (!obj || typeof obj !== 'object') return ''
  const entries = Object.entries(obj)
  const ordered = prefer
    ? prefer.flatMap((k) => (k in obj ? [[k, (obj as any)[k]] as [string, unknown]] : []))
        .concat(entries.filter(([k]) => !prefer.includes(k)))
    : entries
  return ordered
    .slice(0, 5)
    .map(([k, v]) => `${k}=${shortValue(v)}`)
    .join('  ')
}

function shortValue(v: unknown): string {
  if (v == null) return 'null'
  if (typeof v === 'string') return v.length > 48 ? v.slice(0, 45) + '...' : v
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  if (Array.isArray(v)) return `[${v.length}]`
  if (typeof v === 'object') return `{${Object.keys(v as object).length}}`
  return String(v)
}

function shortenForTrace(s: string): string {
  return s.length > 90 ? s.slice(0, 87) + '...' : s
}

function trim<T>(arr: T[], max = 400): T[] {
  return arr.length > max ? arr.slice(arr.length - max) : arr
}
