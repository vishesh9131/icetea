import { useEffect, useState } from 'react'
import { THEME_LABELS, THEMES, type ThemeId } from '../useTheme'

type Props = {
  online: boolean
  busy: boolean
  lastAgent: string | null
  lastLatencyMs: number | null
  blockedCount: number
  collaborative: boolean
  sessionId: string
  theme: ThemeId
  onThemeChange: (t: ThemeId) => void
}

export function StatusBar(p: Props) {
  const [now, setNow] = useState(() => fmtClock())
  useEffect(() => {
    const i = setInterval(() => setNow(fmtClock()), 1000)
    return () => clearInterval(i)
  }, [])

  return (
    <div className="statusbar">
      <span className={`pill ${p.online ? 'ok' : 'err'}`}>
        <span className="dot" /> NET <span className="val">{p.online ? 'LIVE' : 'OFFLINE'}</span>
      </span>
      <span className={`pill ${p.busy ? 'warn' : 'ok'}`}>
        <span className="dot" /> PIPE <span className="val">{p.busy ? 'STREAMING' : 'IDLE'}</span>
      </span>
      <span className="pill">
        LAST AGT <span className="val">{(p.lastAgent || '—').toUpperCase()}</span>
      </span>
      <span className="pill">
        LATENCY <span className="val">{p.lastLatencyMs != null ? `${(p.lastLatencyMs/1000).toFixed(2)}s` : '—'}</span>
      </span>
      <span className={`pill ${p.blockedCount > 0 ? 'err' : ''}`}>
        BLOCKED <span className="val">{p.blockedCount}</span>
      </span>
      <span className={`pill ${p.collaborative ? 'warn' : ''}`}>
        COLLAB <span className="val">{p.collaborative ? 'ON' : 'OFF'}</span>
      </span>
      <span className="pill">
        SES <span className="val">{p.sessionId.slice(-12)}</span>
      </span>
      <span className="spacer" />
      <span className="pill" title="Theme (F12 to cycle)">
        THEME{' '}
        <select
          className="theme-select"
          value={p.theme}
          onChange={(e) => p.onThemeChange(e.target.value as ThemeId)}
        >
          {THEMES.map((t) => (
            <option key={t} value={t}>{THEME_LABELS[t]}</option>
          ))}
        </select>
      </span>
      <span className="clock">{now}</span>
    </div>
  )
}

function fmtClock(): string {
  const d = new Date()
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  return `${hh}:${mm}:${ss} LOC`
}
