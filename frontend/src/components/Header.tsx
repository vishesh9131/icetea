import { useEffect, useState } from 'react'

type Props = {
  model?: string
  provider?: string
  appEnv?: string
  online: boolean
  sessionId: string
}

export function Header(p: Props) {
  const [now, setNow] = useState(() => fmtTime())
  useEffect(() => {
    const i = setInterval(() => setNow(fmtTime()), 1000)
    return () => clearInterval(i)
  }, [])
  return (
    <div className="header">
      <span className="brand">ICETEA TERMINAL</span>
      <span className="meta" style={{ marginLeft: 0 }}>
        <span><span className="key">SES</span> <span className="val">{p.sessionId.slice(0, 18)}</span></span>
      </span>
      <span className="meta">
        <span><span className="key">MODEL</span> <span className="val">{(p.model || '—').slice(-28)}</span></span>
        <span><span className="key">PROV</span> <span className="val">{p.provider || '—'}</span></span>
        <span><span className="key">ENV</span> <span className="val">{p.appEnv || '—'}</span></span>
        <span><span className="key">NET</span> <span className="val" style={{ color: p.online ? 'var(--bg)' : 'red' }}>{p.online ? 'LIVE' : 'DOWN'}</span></span>
        <span><span className="key">UTC</span> <span className="val">{now}</span></span>
      </span>
    </div>
  )
}

function fmtTime(): string {
  const d = new Date()
  const hh = String(d.getUTCHours()).padStart(2, '0')
  const mm = String(d.getUTCMinutes()).padStart(2, '0')
  const ss = String(d.getUTCSeconds()).padStart(2, '0')
  return `${hh}:${mm}:${ss}`
}
