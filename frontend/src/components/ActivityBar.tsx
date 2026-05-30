import { useEffect, useRef, useState } from 'react'
import { OPEN_PALETTE_EVENT } from './CommandBar'
import { TILE_IDS, TILE_LABELS, type TileId } from '../dock/layout'
import { THEMES, THEME_LABELS, type ThemeId } from '../useTheme'

type Props = {
  theme: ThemeId
  onThemeChange: (t: ThemeId) => void
  collaborative: boolean
  onToggleCollab: () => void
  onResetLayout: () => void
  onClearTranscript: () => void
  onReplayOnboarding: () => void
  onOpenBuilder: () => void
  onHelp: () => void
  collapsedTiles: Set<TileId>
  onToggleTile: (t: TileId) => void
}

type MenuId = null | 'file' | 'view' | 'help'

// Left vertical activity bar a la VS Code. Each button either runs an
// action directly or pops a flyout menu to the right. The bar lives at
// grid column 1 of the .terminal grid and spans every row.
export function ActivityBar(props: Props) {
  const [openMenu, setOpenMenu] = useState<MenuId>(null)
  const barRef = useRef<HTMLDivElement>(null)

  // click-outside closes the flyout
  useEffect(() => {
    if (!openMenu) return
    const onClick = (e: MouseEvent) => {
      if (!barRef.current) return
      if (!barRef.current.contains(e.target as Node)) setOpenMenu(null)
    }
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpenMenu(null) }
    window.addEventListener('mousedown', onClick)
    window.addEventListener('keydown', onEsc)
    return () => {
      window.removeEventListener('mousedown', onClick)
      window.removeEventListener('keydown', onEsc)
    }
  }, [openMenu])

  const toggle = (id: MenuId) => setOpenMenu((cur) => (cur === id ? null : id))

  const openPalette = () => {
    // ask the cmdbar to pop its palette via custom event so we dont have
    // to thread state through props
    window.dispatchEvent(new CustomEvent(OPEN_PALETTE_EVENT))
  }

  return (
    <div className="activitybar" ref={barRef}>
      <ActBtn
        label="FILE"
        glyph="≡"
        on={openMenu === 'file'}
        title="File menu"
        onClick={() => toggle('file')}
      />
      <ActBtn
        label="VIEW"
        glyph="▦"
        on={openMenu === 'view'}
        title="View menu (themes + panels)"
        onClick={() => toggle('view')}
      />
      <ActBtn
        label="AGENT"
        glyph="◈"
        title="Agent Builder (Cmd/Ctrl+B)"
        onClick={() => { setOpenMenu(null); props.onOpenBuilder() }}
      />
      <ActBtn
        label="TPLS"
        glyph="▤"
        title="Prompt Templates (Cmd/Ctrl+P)"
        onClick={() => { setOpenMenu(null); openPalette() }}
      />
      <ActBtn
        label="HELP"
        glyph="?"
        on={openMenu === 'help'}
        title="Help menu"
        onClick={() => toggle('help')}
      />

      <div className="act-spacer" />

      <ActBtn
        label="TOUR"
        glyph="↺"
        title="Replay first-run onboarding"
        onClick={() => { setOpenMenu(null); props.onReplayOnboarding() }}
      />

      {/* Flyouts. Positioned absolute relative to .activitybar; the
          buttons are 46px tall so we just `top` them off the right anchor. */}
      {openMenu === 'file' && (
        <FileMenu
          top={4}
          onResetLayout={() => { props.onResetLayout(); setOpenMenu(null) }}
          onClearTranscript={() => { props.onClearTranscript(); setOpenMenu(null) }}
          onReplayOnboarding={() => { props.onReplayOnboarding(); setOpenMenu(null) }}
        />
      )}
      {openMenu === 'view' && (
        <ViewMenu
          top={50}
          theme={props.theme}
          onThemeChange={(t) => { props.onThemeChange(t); /* keep open */ }}
          collaborative={props.collaborative}
          onToggleCollab={() => { props.onToggleCollab(); }}
          collapsedTiles={props.collapsedTiles}
          onToggleTile={(t) => { props.onToggleTile(t) }}
          onClose={() => setOpenMenu(null)}
        />
      )}
      {openMenu === 'help' && (
        <HelpMenu
          top={188}
          onHelp={() => { props.onHelp(); setOpenMenu(null) }}
          onPalette={() => { openPalette(); setOpenMenu(null) }}
          onClose={() => setOpenMenu(null)}
        />
      )}
    </div>
  )
}

// ---- atoms ----

function ActBtn({
  label, glyph, title, onClick, on,
}: { label: string; glyph: string; title: string; onClick: () => void; on?: boolean }) {
  return (
    <button
      className={`act-btn${on ? ' on' : ''}`}
      onClick={onClick}
      title={title}
    >
      <span className="act-glyph" aria-hidden="true">{glyph}</span>
      <span className="act-lbl">{label}</span>
    </button>
  )
}

function FileMenu({
  top, onResetLayout, onClearTranscript, onReplayOnboarding,
}: { top: number; onResetLayout: () => void; onClearTranscript: () => void; onReplayOnboarding: () => void }) {
  return (
    <div className="act-flyout" style={{ top }}>
      <div className="act-fly-head">FILE</div>
      <button className="act-fly-item" onClick={onResetLayout}>
        <span>Reset dock layout</span>
        <span className="act-fly-kbd">⌘⇧R</span>
      </button>
      <button className="act-fly-item" onClick={onClearTranscript}>
        <span>Clear transcript · new session</span>
        <span className="act-fly-kbd">F9 · ^9</span>
      </button>
      <div className="act-fly-sep" />
      <button className="act-fly-item" onClick={onReplayOnboarding}>
        <span>Replay onboarding tour</span>
        <span className="act-fly-kbd">⌘⇧O</span>
      </button>
    </div>
  )
}

function ViewMenu({
  top, theme, onThemeChange, collaborative, onToggleCollab,
  collapsedTiles, onToggleTile, onClose,
}: {
  top: number
  theme: ThemeId
  onThemeChange: (t: ThemeId) => void
  collaborative: boolean
  onToggleCollab: () => void
  collapsedTiles: Set<TileId>
  onToggleTile: (t: TileId) => void
  onClose: () => void
}) {
  return (
    <div className="act-flyout" style={{ top, minWidth: 240 }}>
      <div className="act-fly-head">VIEW</div>
      <div className="act-fly-section">THEME (F12 cycles)</div>
      {THEMES.map((t) => (
        <button
          key={t}
          className={`act-fly-item${t === theme ? ' on' : ''}`}
          onClick={() => onThemeChange(t)}
        >
          <span>{THEME_LABELS[t]}</span>
          {t === theme && <span className="act-fly-kbd">●</span>}
        </button>
      ))}
      <div className="act-fly-sep" />
      <div className="act-fly-section">PANELS (double-click hdr also)</div>
      {TILE_IDS.map((t) => {
        const open = !collapsedTiles.has(t)
        return (
          <button key={t} className="act-fly-item" onClick={() => onToggleTile(t)}>
            <span>{TILE_LABELS[t]}</span>
            <span className="act-fly-kbd">{open ? '[OPEN]' : '[COLLAPSED]'}</span>
          </button>
        )
      })}
      <div className="act-fly-sep" />
      <button className="act-fly-item" onClick={() => { onToggleCollab(); onClose() }}>
        <span>Collaborative pipeline</span>
        <span className="act-fly-kbd">{collaborative ? '[ON] F10' : '[OFF] F10'}</span>
      </button>
    </div>
  )
}

function HelpMenu({
  top, onHelp, onPalette, onClose,
}: { top: number; onHelp: () => void; onPalette: () => void; onClose: () => void }) {
  return (
    <div className="act-flyout" style={{ top }}>
      <div className="act-fly-head">HELP</div>
      <button className="act-fly-item" onClick={onHelp}>
        <span>Show shortcut sheet</span>
        <span className="act-fly-kbd">F8 · ^8</span>
      </button>
      <button className="act-fly-item" onClick={onPalette}>
        <span>Open prompt templates</span>
        <span className="act-fly-kbd">⌘P · ^P</span>
      </button>
      <div className="act-fly-sep" />
      <a
        className="act-fly-item"
        href="https://github.com/vishesh9131/icetea"
        target="_blank"
        rel="noreferrer"
        onClick={onClose}
        style={{ textDecoration: 'none' }}
      >
        <span>Source on GitHub</span>
        <span className="act-fly-kbd">↗</span>
      </a>
      <a
        className="act-fly-item"
        href="https://github.com/vishesh9131/icetea/blob/main/README.md"
        target="_blank"
        rel="noreferrer"
        onClick={onClose}
        style={{ textDecoration: 'none' }}
      >
        <span>README + docs</span>
        <span className="act-fly-kbd">↗</span>
      </a>
    </div>
  )
}
