import { useEffect, useState } from 'react'
import type { Profile } from '../profiles'
import { THUMBS } from './CardThumbs'

export type OnboardingResult = {
  // Operator's display name. Becomes the chosen profile's `name` field on
  // first boot so the PROFILE panel shows their actual name instead of the
  // sample one ("Maya" etc).
  name: string
  // Which preset bucket they picked. "empty" means start with no positions
  // - the operator will add them in the PORT panel themselves.
  profileId: string
}

type Props = {
  // The profile presets fetched from public/profiles.json. Used to populate
  // the portfolio-bucket picker on stage 3.
  profiles: Profile[]
  onComplete: (result: OnboardingResult) => void
}

type Stage = 'splash' | 'name' | 'portfolio' | 'tour'

export function OnboardingFlow({ profiles, onComplete }: Props) {
  const [stage, setStage] = useState<Stage>('splash')
  const [name, setName] = useState('')
  const [profileId, setProfileId] = useState<string>('')
  const [tourIdx, setTourIdx] = useState(0)

  // ESC at any time skips the whole flow with sensible defaults.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onComplete({
          name: name.trim() || 'OPERATOR',
          profileId: profileId || (profiles[0]?.id ?? 'empty'),
        })
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [name, profileId, profiles, onComplete])

  // ---- stage 1: title splash ----------------------------------------
  if (stage === 'splash') {
    return <SplashStage onDone={() => setStage('name')} />
  }

  // ---- stage 2: name --------------------------------------------------
  if (stage === 'name') {
    return (
      <div className="onb-overlay">
        <div className="onb-card onb-stage">
          <StageHeader step={1} total={3} title="WHO ARE YOU" />
          <p className="onb-prose">
            What should the terminal call you? Used only inside this browser —
            shown in the PROFILE panel + when agents address you by name.
          </p>
          <form
            className="onb-form"
            onSubmit={(e) => {
              e.preventDefault()
              if (name.trim()) setStage('portfolio')
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

  // ---- stage 3: portfolio bucket --------------------------------------
  if (stage === 'portfolio') {
    return (
      <div className="onb-overlay">
        <div className="onb-card onb-stage onb-wide">
          <StageHeader step={2} total={3} title="YOUR BOOK" />
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
            <button className="onb-btn" onClick={() => setStage('name')}>&larr; BACK</button>
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
      <div className="onb-card onb-stage onb-wide">
        <div className="onb-card-head-row">
          <StageHeader step={3} total={3} title="WHAT IT CAN DO" />
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
              onClick={() => onComplete({ name: name.trim(), profileId })}
            >LAUNCH TERMINAL &rarr;</button>
          )}
        </div>
        <div className="onb-hint">arrow keys to navigate · esc to skip</div>
      </div>
    </div>
  )
}

// ----- helpers --------------------------------------------------------

// Title-only splash. Auto-advances after a few seconds so the operator
// doesn't sit on a static screen, but they can also click anywhere to
// skip straight to the name prompt.
const SPLASH_HOLD_MS = 2400

function SplashStage({ onDone }: { onDone: () => void }) {
  useEffect(() => {
    const id = setTimeout(onDone, SPLASH_HOLD_MS)
    return () => clearTimeout(id)
  }, [onDone])

  return (
    <div className="onb-overlay">
      <div className="onb-splash">
        <div className="onb-title-block">
          <div className="onb-title">ICETEA</div>
          <div className="onb-title-rule" />
          <div className="onb-tag">your own AI co-investor team, on your desk.</div>
          <div className="onb-skip">click anywhere to continue · esc to skip</div>
        </div>
        <button
          className="onb-skip-target"
          onClick={onDone}
          aria-label="continue"
        />
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
