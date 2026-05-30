import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ChatMessage } from '../types'

type Props = {
  messages: ChatMessage[]
  streaming: boolean
}

export function ChatPanel({ messages, streaming }: Props) {
  const logRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Auto-scroll to bottom on every new chunk. If a user is reading older
    // content theyll just scroll up, which is the right default for a chat.
    const el = logRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [messages, streaming])

  return (
    <div className="chat-log" ref={logRef}>
      {messages.length === 0 && (
        <div className="chat-msg sys">
          <div className="meta-row">
            <span className="role">SYS</span>
            <span className="agent-tag">ICETEA</span>
            <span className="ts">{nowStr()}</span>
          </div>
          <div className="body">
{`> ICETEA TERMINAL ready. Type a query and press ENTER, or hit a function key.

  F1 CHAT   F2 PORT   F3 RISK   F4 MR     F5 STRAT
  F6 DEBATE F7 PLAN   F8 HELP   F9 CLEAR  F10 COLLAB

  Examples:
    > how is my portfolio doing?
    > stress test if the market drops 30%
    > should i sell half of NVDA?
    > recommend an ESG global equity ETF
    > what is insider trading?  (educational, allowed)`}
          </div>
        </div>
      )}
      {messages.map((m) => (
        <MessageRow key={m.id} m={m} />
      ))}
    </div>
  )
}

function MessageRow({ m }: { m: ChatMessage }) {
  const [showJson, setShowJson] = useState(false)
  const klass = m.role === 'user' ? 'user' : m.role === 'error' ? 'err' : m.role === 'system' ? 'sys' : 'bot'
  const role  = m.role === 'user' ? 'YOU' : m.role === 'error' ? 'ERR' : m.role === 'system' ? 'SYS' : 'AGT'
  const agentTag = m.blocked
    ? `BLOCKED${m.blockCategory ? ' / ' + m.blockCategory.toUpperCase() : ''}`
    : (m.agent || 'PIPELINE').toUpperCase()
  return (
    <div className={`chat-msg ${klass}`}>
      <div className="meta-row">
        <span className="role">{role}</span>
        <span className="agent-tag">{agentTag}{m.collaborative ? ' / COLLAB' : ''}</span>
        <span className="ts">{tsStr(m.ts)}</span>
        {typeof m.latencyMs === 'number' && (
          <span className="latency">{(m.latencyMs / 1000).toFixed(1)}s</span>
        )}
      </div>
      <div className={`body${useMarkdown(m) ? ' body-md' : ''}`}>
        {useMarkdown(m)
          ? <MarkdownBody text={m.text} />
          : m.text}
        {m.streaming && m.progress && !m.text && (
          <ProgressStrip progress={m.progress} />
        )}
        {m.streaming && <span className="cursor" />}
      </div>
      {m.structured && Object.keys(m.structured).length > 0 && (
        <>
          <div className="structured-toggle" onClick={() => setShowJson((v) => !v)}>
            [{showJson ? '−' : '+'}] STRUCTURED PAYLOAD ({Object.keys(m.structured).length} KEYS)
          </div>
          {showJson && (
            <pre className="structured">{JSON.stringify(m.structured, null, 2)}</pre>
          )}
        </>
      )}
    </div>
  )
}

// Markdown rendering applies to assistant (bot) replies only. We leave the
// USER bubble, SYS HELP screen and ERR bubbles as raw monospace so they
// keep their terminal-y feel. The assistant body switches to a sans-serif
// "chat" font similar to what ChatGPT renders.
function useMarkdown(m: ChatMessage): boolean {
  return m.role === 'assistant' && !m.blocked && !!m.text
}

function MarkdownBody({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        // Open every link in a new tab and dim styling so it reads in dark theme
        a: ({ node: _node, ...props }) => (
          <a {...props} target="_blank" rel="noopener noreferrer" />
        ),
        // Disallow rendering raw HTML through markdown - we never want a streamed
        // token blob to inject HTML into the page.
        // (react-markdown 9 already disables html by default, this is belt+braces)
      }}
    >
      {text}
    </ReactMarkdown>
  )
}

function ProgressStrip({ progress }: { progress: NonNullable<ChatMessage['progress']> }) {
  // Quiet status line shown while the collaborative supervisor is still
  // talking to its agents and no tokens have streamed yet. Lets the user
  // see "round 4 / risk_assessment running..." instead of a blank cursor.
  const round = typeof progress.round === 'number' ? `r${progress.round}` : ''
  const agent = (progress.agent || progress.stage).toUpperCase()
  return (
    <div className="progress-strip">
      {`> running ${agent}${round ? ' [' + round + ']' : ''}…`}
    </div>
  )
}

function nowStr(): string {
  return tsStr(Date.now())
}

function tsStr(ms: number): string {
  const d = new Date(ms)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  return `${hh}:${mm}:${ss}`
}
