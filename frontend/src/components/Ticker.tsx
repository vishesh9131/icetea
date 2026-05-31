import { useEffect, useRef, useState } from 'react'
import { fetchTape, type TapeItem } from '../sseClient'

// How often we hit /v1/market/tape. The backend caches for 45s so anything
// below that just hits the cache - 30s gives us roughly two stale-then-fresh
// cycles per minute, which keeps the ribbon feeling alive without spamming
// uvicorn from every tab on every focus change.
const POLL_MS = 30_000
// when we're in an error state (backend just booted, transient blip, etc)
// we burst-poll on a short backoff so the ribbon recovers in seconds rather
// than waiting the full 30s window.
const ERROR_BACKOFF_MS = [2_000, 4_000, 8_000, 15_000]

type State = {
  items: TapeItem[]
  stale: boolean    // backend served cached/stale while refreshing
  offline: boolean  // last fetch failed entirely
  loading: boolean
}

export function Ticker() {
  const [state, setState] = useState<State>({ items: [], stale: false, offline: false, loading: true })
  // keep last good items so we never blank out the ribbon between polls
  const lastGoodRef = useRef<TapeItem[]>([])

  useEffect(() => {
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | null = null
    // failures back to back - used to walk up the backoff table so we don't
    // hammer the backend if it's actually down, but recover fast if it's
    // just starting up.
    let failStreak = 0
    const tick = async () => {
      const data = await fetchTape()
      if (stopped) return
      let nextDelay: number
      if (data && Array.isArray(data.items) && data.items.length > 0) {
        lastGoodRef.current = data.items
        setState({ items: data.items, stale: !!data.stale, offline: false, loading: false })
        failStreak = 0
        nextDelay = POLL_MS
      } else {
        setState({ items: lastGoodRef.current, stale: true, offline: true, loading: false })
        nextDelay = ERROR_BACKOFF_MS[Math.min(failStreak, ERROR_BACKOFF_MS.length - 1)]
        failStreak += 1
      }
      timer = setTimeout(tick, nextDelay)
    }
    tick()
    return () => { stopped = true; if (timer) clearTimeout(timer) }
  }, [])

  // Doubling the list is what gives the marquee its seamless loop in CSS.
  const items = state.items.length > 0 ? state.items : []
  const doubled = [...items, ...items]

  return (
    <div className={`ticker${state.stale ? ' stale' : ''}${state.offline ? ' offline' : ''}`}>
      <div className="ticker-track">
        {state.loading && items.length === 0 && (
          <span className="ticker-item">
            <span className="sym">TAPE</span>
            <span className="flat">connecting...</span>
          </span>
        )}
        {state.offline && items.length === 0 && (
          <span className="ticker-item">
            <span className="sym">TAPE</span>
            <span className="down">offline · check /v1/market/tape</span>
          </span>
        )}
        {doubled.map((it, i) => (
          <TickerCell key={`${it.sym}-${i}`} it={it} />
        ))}
      </div>
    </div>
  )
}

function TickerCell({ it }: { it: TapeItem }) {
  if (it.error || it.last == null) {
    return (
      <span className="ticker-item">
        <span className="sym">{it.sym}</span>
        <span className="flat">--</span>
      </span>
    )
  }
  const change = it.change_pct
  const dir: 'up' | 'down' | 'flat' =
    change == null ? 'flat' : change > 0.01 ? 'up' : change < -0.01 ? 'down' : 'flat'
  const sign = change != null && change > 0 ? '+' : ''
  const chgText = change == null ? '   --   ' : `${sign}${change.toFixed(2)}%`
  return (
    <span className="ticker-item">
      <span className="sym">{it.sym}</span>
      <span className={dir}>{formatPrice(it.last, it.unit)} {chgText}</span>
    </span>
  )
}

function formatPrice(v: number, unit: string | null): string {
  // FX (under 10) wants 4 decimals; rates (US10Y) want 3 decimals; everything
  // else gets thousand-grouped 2-decimal so big indices read as "5,478.34".
  if (unit === '%') return `${v.toFixed(3)}%`
  if (Math.abs(v) < 10) return v.toFixed(4)
  return v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
