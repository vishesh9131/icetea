import { useEffect, useState } from 'react'
import type { Profile } from '../profiles'
import { fetchProviders, type LlmProviderId, type ProviderInfo } from '../sseClient'
import { THUMBS } from './CardThumbs'
import { AsciiBackdrop } from './AsciiBackdrop'
// shipped as a static text asset so we don't have to inline 300 columns of
// ascii into a .tsx string literal. Vite's `?raw` loader returns the file
// contents verbatim at build time.
import asciiTitle from './icetea-title.txt?raw'

export type OnboardingResult = {
  // Operator's display name. Becomes the chosen profile's `name` field on
  // first boot so the PROFILE panel shows their actual name instead of the
  // sample one ("Maya" etc).
  name: string
  // Which preset bucket they picked. "empty" means start with no positions
  // - the operator will add them in the PORT panel themselves.
  profileId: string
  // Which LLM the pipeline should call into. The choice is POSTed to the
  // backend so every subsequent /v1/chat hits the right provider.
  llmProvider: LlmProviderId
}

type Props = {
  // The profile presets fetched from public/profiles.json. Used to populate
  // the portfolio-bucket picker on stage 3.
  profiles: Profile[]
  onComplete: (result: OnboardingResult) => void
}

type Stage = 'splash' | 'name' | 'provider' | 'portfolio' | 'tour'

const STAGE_TOTAL = 4 // name, provider, portfolio, tour

const DEFAULT_PROVIDER: LlmProviderId = 'vllm'

export function OnboardingFlow({ profiles, onComplete }: Props) {
  const [stage, setStage] = useState<Stage>('splash')
  const [name, setName] = useState('')
  const [profileId, setProfileId] = useState<string>('')
  const [llmProvider, setLlmProvider] = useState<LlmProviderId>(DEFAULT_PROVIDER)
  const [providers, setProviders] = useState<ProviderInfo[] | null>(null)
  const [tourIdx, setTourIdx] = useState(0)

  // Load the provider list as soon as we mount so the picker has data
  // ready by the time the operator reaches stage 2. If the backend is
  // offline we fall back to a hard-coded shell so the UX still works.
  useEffect(() => {
    let stopped = false
    fetchProviders().then((p) => {
      if (stopped) return
      if (p?.providers?.length) {
        setProviders(p.providers)
        setLlmProvider(p.active || DEFAULT_PROVIDER)
      } else {
        setProviders(FALLBACK_PROVIDERS)
      }
    })
    return () => { stopped = true }
  }, [])

  // ESC at any time skips the whole flow with sensible defaults.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onComplete({
          name: name.trim() || 'OPERATOR',
          profileId: profileId || (profiles[0]?.id ?? 'empty'),
          llmProvider,
        })
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [name, profileId, profiles, llmProvider, onComplete])

  // ---- stage 1: title splash ----------------------------------------
  if (stage === 'splash') {
    return <SplashStage onDone={() => setStage('name')} />
  }

  // ---- stage 2: name --------------------------------------------------
  if (stage === 'name') {
    return (
      <div className="onb-overlay">
        <AsciiBackdrop crop="right" />
        <div className="onb-card onb-stage">
          <StageHeader step={1} total={STAGE_TOTAL} title="WHO ARE YOU" />
          <p className="onb-prose">
            What should the terminal call you? Used only inside this browser —
            shown in the PROFILE panel + when agents address you by name.
          </p>
          <form
            className="onb-form"
            onSubmit={(e) => {
              e.preventDefault()
              if (name.trim()) setStage('provider')
            }}
          >
            <input
              className="onb-input"
              autoFocus
              placeholder="e.g. Vishesh"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={40}
            />
            <button
              className="onb-btn primary"
              type="submit"
              disabled={!name.trim()}
            >
              NEXT &rarr;
            </button>
          </form>
          <div className="onb-hint">enter to continue · esc to skip</div>
        </div>
      </div>
    )
  }

  // ---- stage 3: LLM provider ------------------------------------------
  if (stage === 'provider') {
    const list = providers ?? FALLBACK_PROVIDERS
    return (
      <div className="onb-overlay">
        <AsciiBackdrop crop="left" />
        <div className="onb-card onb-stage onb-wide">
          <StageHeader step={2} total={STAGE_TOTAL} title="PICK YOUR BRAIN" />
          <p className="onb-prose">
            Which LLM should drive the agent team? You can switch later from
            the activity bar &rarr; VIEW menu — nothing locks you in. Providers
            without a server-side key show up dim until you set them in
            <code> backend/.env</code>.
          </p>
          <div className="onb-provider-grid">
            {list.map((p) => (
              <button
                key={p.id}
                type="button"
                className={
                  'onb-provider'
                  + (llmProvider === p.id ? ' active' : '')
                  + (!p.configured ? ' disabled' : '')
                }
                onClick={() => { if (p.configured) setLlmProvider(p.id) }}
                disabled={!p.configured}
                title={!p.configured ? `${p.label} - ${p.note}` : p.label}
              >
                <div className="onb-provider-head">
                  <span className="onb-provider-radio" aria-hidden="true">
                    {llmProvider === p.id ? '(*)' : '( )'}
                  </span>
                  <span className="onb-provider-id">{p.id.toUpperCase()}</span>
                  {!p.configured && <span className="onb-provider-tag">NO KEY</span>}
                </div>
                <div className="onb-provider-label">{p.label}</div>
                <div className="onb-provider-model">model: {p.model || '—'}</div>
                <div className="onb-provider-note">{p.note}</div>
              </button>
            ))}
          </div>
          <div className="onb-row">
            <button className="onb-btn" onClick={() => setStage('name')}>&larr; BACK</button>
            <button
              className="onb-btn primary"
              onClick={() => setStage('portfolio')}
            >NEXT &rarr;</button>
          </div>
          <div className="onb-hint">switchable any time · esc to skip</div>
        </div>
      </div>
    )
  }

  // ---- stage 4: portfolio bucket --------------------------------------
  if (stage === 'portfolio') {
    return (
      <div className="onb-overlay">
        <AsciiBackdrop crop="bottom-right" />
        <div className="onb-card onb-stage onb-wide">
          <StageHeader step={3} total={STAGE_TOTAL} title="YOUR BOOK" />
          <p className="onb-prose">
            Pick a starter book to demo the system, or start empty and enter
            your real positions in the PORT panel after launch. You can
            switch books at any time from the PROFILE dropdown.
          </p>
          <div className="onb-bucket-grid">
            {profiles.map((p) => {
              const positions = p.ctx.positions || []
              const isEmpty = positions.length === 0
              return (
                <button
                  key={p.id}
                  className={`onb-bucket${profileId === p.id ? ' active' : ''}`}
                  onClick={() => setProfileId(p.id)}
                >
                  <div className="onb-bucket-id">{p.label.split(' — ')[0] || p.id.toUpperCase()}</div>
                  <div className="onb-bucket-desc">
                    {p.label.includes(' — ') ? p.label.split(' — ')[1] : p.label}
                  </div>
                  <div className="onb-bucket-stats">
                    {isEmpty ? (
                      <span>no positions · build your own</span>
                    ) : (
                      <span>
                        {positions.length} pos · {topTickers(positions)}
                      </span>
                    )}
                  </div>
                </button>
              )
            })}
          </div>
          <div className="onb-row">
            <button className="onb-btn" onClick={() => setStage('provider')}>&larr; BACK</button>
            <button
              className="onb-btn primary"
              disabled={!profileId}
              onClick={() => setStage('tour')}
            >NEXT &rarr;</button>
          </div>
          <div className="onb-hint">esc to skip</div>
        </div>
      </div>
    )
  }

  // ---- stage 4: capability tour ---------------------------------------
  const card = CAPABILITIES[tourIdx]
  const lastCard = tourIdx === CAPABILITIES.length - 1
  const Thumb = THUMBS[tourIdx]
  return (
    <div className="onb-overlay" onKeyDown={(e) => {
      if (e.key === 'ArrowRight') { e.preventDefault(); if (!lastCard) setTourIdx(tourIdx + 1) }
      if (e.key === 'ArrowLeft')  { e.preventDefault(); if (tourIdx > 0) setTourIdx(tourIdx - 1) }
    }} tabIndex={-1}>
      <AsciiBackdrop crop="top" />
      <div className="onb-card onb-stage onb-wide">
        <div className="onb-card-head-row">
          <StageHeader step={4} total={STAGE_TOTAL} title="WHAT IT CAN DO" />
          <div className="onb-card-num">{(tourIdx + 1).toString().padStart(2, '0')} / {CAPABILITIES.length.toString().padStart(2, '0')}</div>
        </div>
        <div className="onb-thumb-wrap">
          {Thumb ? <Thumb /> : null}
        </div>
        <div className="onb-card-title">{card.title}</div>
        <ul className="onb-card-bullets">
          {card.bullets.map((b, i) => <li key={i}>{b}</li>)}
        </ul>
        <div className="onb-card-kbd">{card.kbd}</div>

        <div className="onb-dots">
          {CAPABILITIES.map((_, i) => (
            <button
              key={i}
              className={`onb-dot${i === tourIdx ? ' active' : ''}`}
              onClick={() => setTourIdx(i)}
              aria-label={`go to card ${i + 1}`}
            />
          ))}
        </div>

        <div className="onb-row">
          <button
            className="onb-btn"
            disabled={tourIdx === 0}
            onClick={() => setTourIdx(tourIdx - 1)}
          >&larr; PREV</button>
          {!lastCard ? (
            <button className="onb-btn primary" onClick={() => setTourIdx(tourIdx + 1)} autoFocus>NEXT &rarr;</button>
          ) : (
            <button
              className="onb-btn primary"
              autoFocus
              onClick={() => onComplete({ name: name.trim(), profileId, llmProvider })}
            >LAUNCH TERMINAL &rarr;</button>
          )}
        </div>
        <div className="onb-hint">arrow keys to navigate · esc to skip</div>
      </div>
    </div>
  )
}

// ----- helpers --------------------------------------------------------

// Title splash. No auto-advance any more - the operator clicks GET STARTED
// when they're ready. Enter key also fires it for keyboard-first users.
function SplashStage({ onDone }: { onDone: () => void }) {
  // belt-and-braces: if vite/HMR ever ships an empty raw import (it shouldnt,
  // but we saw a grey-flash during fast refresh) fall back to a plain
  // wordmark so the splash is never visually blank.
  const art = (asciiTitle && asciiTitle.trim().length > 0)
    ? asciiTitle
    : 'I C E T E A'

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        onDone()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onDone])

  return (
    <div className="onb-overlay">
      <div className="onb-splash">
        <div className="onb-title-block">
          {/* the trimmed ascii is ~79 rows x 298 cols - CSS scales the
              font down so it sits inside a compact block, with line-height
              crunched so the vertical footprint stays reasonable */}
          <pre className="onb-ascii-title" aria-label="ICETEA">{art}</pre>
          <div className="onb-tag">your own AI co-investor team, on your desk.</div>
          <button
            className="onb-btn primary onb-cta"
            onClick={onDone}
            type="button"
            autoFocus
          >
            GET STARTED &rarr;
          </button>
          <div className="onb-skip">press enter · or hit escape to skip the whole flow</div>
        </div>
      </div>
    </div>
  )
}

function StageHeader({ step, total, title }: { step: number; total: number; title: string }) {
  return (
    <div className="onb-stage-head">
      <span className="onb-stage-step">[{step}/{total}]</span>
      <span className="onb-stage-title">{title}</span>
    </div>
  )
}

function topTickers(positions: { ticker: string }[]): string {
  const t = positions.slice(0, 4).map((p) => p.ticker).join(', ')
  return positions.length > 4 ? `${t}, +${positions.length - 4}` : t
}

// ----- capability cards content --------------------------------------
//
// Each card declares its text only - the animated dense-ASCII thumbnail
// comes from `THUMBS[i]` in CardThumbs.tsx, indexed in the same order
// as this array. Keep them aligned!

type Capability = {
  title: string
  bullets: string[]
  kbd: string
}

// Backend-offline fallback for the provider picker. Keeps the onboarding
// usable when /v1/runtime/llm-providers cant be reached on first paint
// (e.g. operator opens the UI before uvicorn finishes booting).
const FALLBACK_PROVIDERS: ProviderInfo[] = [
  { id: 'vllm',   label: 'vLLM (self-hosted)',  model: 'default',                       base_url: 'https://vllm.corerec.online/v1', configured: true,  note: 'free · runs on your tunnel' },
  { id: 'openai', label: 'OpenAI',              model: 'gpt-4o-mini',                   base_url: 'https://api.openai.com/v1',      configured: false, note: 'needs OPENAI_API_KEY' },
  { id: 'claude', label: 'Anthropic Claude',    model: 'claude-3-5-sonnet-20241022',    base_url: 'https://api.anthropic.com/v1/',  configured: false, note: 'needs ANTHROPIC_API_KEY' },
]

const CAPABILITIES: Capability[] = [
  {
    title: 'AI CO-INVESTOR TEAM',
    bullets: [
      'a panel of specialist agents - portfolio health, planning, strategy, risk, debate',
      'F10 toggles a collaborative pipeline where multiple agents argue + converge',
      'safety guard blocks pump-and-dump, insider, manipulation prompts before any LLM call',
    ],
    kbd: 'F1 focus chat  ·  F10 toggle collab',
  },
  {
    title: 'PORTFOLIO + RISK',
    bullets: [
      'inline-editable book - ticker, qty, cost, currency, all live',
      'deterministic concentration / beta / scenario math under the LLM narrative',
      '"stress test if NVDA drops 30%" runs the numbers and explains the why',
    ],
    kbd: 'F2 portfolio  ·  F3 risk',
  },
  {
    title: 'LIVE NEWS + IN-APP READER',
    bullets: [
      'real-time yfinance headlines for the market basket + your holdings',
      'click any headline to read the article inline - no browser tabs',
      'articles fetched server-side, SSRF-filtered, paragraph-cleaned',
    ],
    kbd: 'click a row  ·  Ctrl+5 focus news  ·  Ctrl+6 reader',
  },
  {
    title: 'BRING YOUR OWN AGENT',
    bullets: [
      'mint a custom agent: id, label, system prompt, MCP/web tool picks',
      '22 tools available out of the box - DuckDuckGo search + 20 MCP endpoints',
      'persists to disk, survives restarts, no code editing required',
    ],
    kbd: 'Ctrl+B opens the AGENT BUILDER overlay',
  },
  {
    title: 'DOCK + KEYBOARD WORKSPACE',
    bullets: [
      'every panel is drag-resizable, drag-to-swap, double-click to collapse',
      'Ctrl+1..6 focus tile  ·  Ctrl+Shift+arrows resize  ·  Ctrl+Shift+R reset',
      'F12 cycles 5 themes - amber, teal, CRT green, ice blue, paperwhite',
    ],
    kbd: 'F8 opens the full HELP screen',
  },
]
