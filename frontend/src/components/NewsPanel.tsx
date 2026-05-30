import { useEffect, useMemo, useState } from 'react'
import { fetchMarketNews, fetchPortfolioNews, type NewsItem } from '../sseClient'
import type { UserContext } from '../types'

type Mode = 'market' | 'portfolio'

const REFRESH_MS = 60_000 // backend caches 5 min per ticker; we poll once a minute

type Props = {
  ctx: UserContext
  onOpenArticle?: (item: NewsItem) => void
}

export function NewsPanel({ ctx, onOpenArticle }: Props) {
  const [mode, setMode] = useState<Mode>('market')
  const [items, setItems] = useState<NewsItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [asOf, setAsOf] = useState<number | null>(null)

  // Portfolio mode keys off the user's holdings - we want the news to refresh
  // when they edit the portfolio (e.g. add a new ticker).
  const tickerKey = useMemo(
    () => ctx.positions.map((p) => p.ticker.toUpperCase()).sort().join(','),
    [ctx.positions],
  )

  useEffect(() => {
    let stopped = false
    const run = async () => {
      setLoading(true)
      setError(null)
      const data = mode === 'market'
        ? await fetchMarketNews()
        : await fetchPortfolioNews(tickerKey.split(',').filter(Boolean))
      if (stopped) return
      if (!data) {
        setError('news endpoint unreachable')
        setItems([])
      } else if (mode === 'portfolio' && (!data.tickers || data.tickers.length === 0)) {
        setError('no positions in this profile')
        setItems([])
      } else {
        setItems(data.items || [])
        setAsOf(data.as_of)
      }
      setLoading(false)
    }
    run()
    const id = setInterval(run, REFRESH_MS)
    return () => { stopped = true; clearInterval(id) }
  }, [mode, tickerKey])

  return (
    <div className="news-panel">
      <div className="news-controls">
        <div className="news-tabs">
          <button
            className={`news-tab${mode === 'market' ? ' active' : ''}`}
            onClick={() => setMode('market')}
          >MARKET</button>
          <button
            className={`news-tab${mode === 'portfolio' ? ' active' : ''}`}
            onClick={() => setMode('portfolio')}
          >PORTFOLIO</button>
        </div>
        <div className="news-meta">
          {loading && <span>refreshing…</span>}
          {!loading && asOf && <span>as of {fmtTime(asOf)}</span>}
          {!loading && items.length > 0 && <span>{items.length} items</span>}
        </div>
      </div>
      <div className="news-list">
        {error && (
          <div className="news-empty">
            {error}
            {mode === 'portfolio' && error.includes('no positions') && (
              <div style={{ marginTop: 4, fontSize: 10.5, opacity: 0.7 }}>
                switch profile or add a position in PORT
              </div>
            )}
          </div>
        )}
        {!error && !loading && items.length === 0 && (
          <div className="news-empty">no items</div>
        )}
        {items.map((it) => (
          <NewsRow key={it.id} item={it} onOpen={onOpenArticle} />
        ))}
      </div>
    </div>
  )
}

function NewsRow({ item, onOpen }: { item: NewsItem; onOpen?: (i: NewsItem) => void }) {
  const ts = item.published_ts
  const rel = ts ? relTime(ts * 1000) : ''
  // Click opens the article in the READER dock tile. Shift/Cmd/Ctrl+Click
  // still opens in a new browser tab so power users can escape the in-app
  // reader when they want the full rich page.
  const onClick = (e: React.MouseEvent) => {
    if (e.shiftKey || e.metaKey || e.ctrlKey) return  // let the <a> default fire
    e.preventDefault()
    if (onOpen) onOpen(item)
  }
  return (
    <a
      className="news-row"
      href={item.url || '#'}
      target="_blank"
      rel="noopener noreferrer"
      title={`click to open in READER — \u2318/Ctrl/Shift click to open externally`}
      onClick={onClick}
    >
      <div className="news-row-meta">
        <span className="news-source">{(item.source || '?').toUpperCase()}</span>
        {item.tickers.length > 0 && (
          <span className="news-tickers">{item.tickers.join(', ')}</span>
        )}
        <span className="news-time">{rel}</span>
      </div>
      <div className="news-title">{item.title}</div>
      {item.summary && (
        <div className="news-summary">{truncate(item.summary, 180)}</div>
      )}
    </a>
  )
}

function fmtTime(epochS: number): string {
  const d = new Date(epochS * 1000)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

function relTime(ms: number): string {
  const dt = (Date.now() - ms) / 1000
  if (dt < 60) return `${Math.floor(dt)}s ago`
  if (dt < 3600) return `${Math.floor(dt / 60)}m ago`
  if (dt < 86_400) return `${Math.floor(dt / 3600)}h ago`
  return `${Math.floor(dt / 86_400)}d ago`
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + '…' : s
}
