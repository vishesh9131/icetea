import { useEffect, useRef } from 'react'
import type { TraceEntry } from '../types'

type Props = {
  entries: TraceEntry[]
}

export function AgentTracePanel({ entries }: Props) {
  const bodyRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = bodyRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [entries])

  return (
    <div className="panel-body trace" ref={bodyRef}>
      {entries.length === 0 && (
        <div className="muted" style={{ padding: '4px 0' }}>
          no events yet — send a query
        </div>
      )}
      {entries.map((e) => (
        <div className="trace-row" key={e.id}>
          <span className="t">{tsStr(e.ts)}</span>
          <span className={`ev ${e.kind}`}>{e.label}</span>
          <span className="body">{e.body}</span>
        </div>
      ))}
    </div>
  )
}

function tsStr(ms: number): string {
  const d = new Date(ms)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  const ms3 = String(d.getMilliseconds()).padStart(3, '0')
  return `${hh}:${mm}:${ss}.${ms3.slice(0, 2)}`
}
