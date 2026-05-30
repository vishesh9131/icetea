import { useEffect, useState } from 'react'
import { fetchArticle, type ArticlePayload } from '../sseClient'
import type { NewsItem } from '../sseClient'

type Props = {
  article: NewsItem | null
}

export function ReaderPanel({ article }: Props) {
  const [payload, setPayload] = useState<ArticlePayload | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let stopped = false
    if (!article || !article.url) {
      setPayload(null)
      setError(null)
      return
    }
    setLoading(true)
    setError(null)
    setPayload(null)
    fetchArticle(article.url).then((p) => {
      if (stopped) return
      setLoading(false)
      if (!p) { setError('reader endpoint unreachable'); return }
      if (!p.ok) { setError(p.note || 'fetch failed'); return }
      setPayload(p)
    })
    return () => { stopped = true }
  }, [article?.url])

  if (!article) {
    return (
      <div className="reader-panel">
        <div className="reader-empty">
          click any headline in NEWS to open it here
          <div style={{ marginTop: 6, fontSize: 10.5, opacity: 0.7 }}>
            articles are fetched server-side (SSRF-filtered) and rendered
            as plain text - no external tab is opened.
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="reader-panel">
      <div className="reader-head">
        <div className="reader-meta">
          <span className="reader-source">{(article.source || '?').toUpperCase()}</span>
          {article.tickers.length > 0 && (
            <span className="reader-tickers">{article.tickers.join(', ')}</span>
          )}
          {article.published_at && (
            <span className="reader-time">{formatPub(article.published_at)}</span>
          )}
        </div>
        <div className="reader-title">{article.title}</div>
        {article.url && (
          <div className="reader-url">
            <a
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              title="open the original article in a new browser tab"
            >open original ↗</a>
            <span className="reader-url-text">{truncate(article.url, 90)}</span>
          </div>
        )}
      </div>
      <div className="reader-body">
        {loading && <div className="reader-status">fetching…</div>}
        {error && (
          <div className="reader-status reader-error">
            could not extract article body: {error}
            {article.summary && (
              <div style={{ marginTop: 12, color: 'var(--amber)' }}>
                <div style={{ fontSize: 10, opacity: 0.7, marginBottom: 4 }}>SUMMARY (yfinance):</div>
                {article.summary}
              </div>
            )}
          </div>
        )}
        {payload && payload.ok && (
          <article className="reader-text">
            {payload.text.split(/\n{2,}/).map((para, i) => (
              <p key={i}>{para}</p>
            ))}
            {payload.text.length >= 12000 && (
              <p className="reader-truncated">
                — truncated at 12 000 chars · click "open original" above for the full article
              </p>
            )}
          </article>
        )}
      </div>
    </div>
  )
}

function formatPub(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString(undefined, {
      month: 'short', day: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + '…' : s
}
