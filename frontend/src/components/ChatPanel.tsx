import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ChatMessage } from '../types'

type Props = {
  messages: ChatMessage[]
  streaming: boolean
  // toggle the collapsed/expanded state of a message's thinking pane.
  // App owns the messages array so the toggle lives in the parent.
  onToggleThinking?: (id: string) => void
}

export function ChatPanel({ messages, streaming, onToggleThinking }: Props) {
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
        <MessageRow key={m.id} m={m} onToggleThinking={onToggleThinking} />
      ))}
    </div>
  )
}

function MessageRow({
  m,
  onToggleThinking,
}: {
  m: ChatMessage
  onToggleThinking?: (id: string) => void
}) {
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
      {m.thinking && (
        <ThinkingBlock
          text={m.thinking}
          open={m.thinkingOpen ?? false}
          streaming={!!m.streaming && !m.text}
          onToggle={() => onToggleThinking?.(m.id)}
        />
      )}
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

// "Thinking..." strip - short fixed-height viewport into the model's
// chain-of-thought. New tokens arrive at the bottom, the whole transcript
// pushes upward like a teleprompter, and the top + bottom edges fade out
// (CSS mask + perspective transform) so the visible band reads like a
// slice of a horizontal cylinder rotating past you. The pre is auto-
// scrolled to the tail on every token so the user always sees the newest
// thought without having to chase it.
function ThinkingBlock({
  text,
  open,
  streaming,
  onToggle,
}: {
  text: string
  open: boolean
  streaming: boolean
  onToggle: () => void
}) {
  const chars = text.length
  // very rough token estimate (~4 chars / token for English). Cheap to compute,
  // good enough to give a sense of "how much CoT was produced".
  const tokens = Math.max(1, Math.round(chars / 4))
  const bodyRef = useRef<HTMLPreElement>(null)
  useEffect(() => {
    const el = bodyRef.current
    if (!el || !open) return
    // We drive position via translateY (not scrollTop) because the body
    // already has a rotateX + translateZ on it for the cylinder feel, and
    // mixing that with CSS scroll-behavior: smooth caused the browser to
    // clamp scroll writes to ~0. Transform-based motion is also genuinely
    // smooth: the CSS transition on .thinking-body interpolates between
    // each translateY value automatically.
    //
    // The target keeps the active write line 3 lines BELOW the visible
    // bottom (i.e. inside the bottom fade), so the operator reads settled
    // text instead of chasing the cursor.
    const lh = parseFloat(getComputedStyle(el).lineHeight) || 17
    const trailingLines = 3
    const offset = trailingLines * lh
    const viewport = el.parentElement
    const viewportH = viewport ? viewport.clientHeight : el.clientHeight
    const contentH = el.scrollHeight
    // We want the bottom edge of the viewport to align with the line that
    // is `trailingLines` rows BEFORE the end of content. That keeps the
    // active write line, plus a couple of buffer rows, hidden below the
    // bottom fade. Math: shift up by overflow MINUS offset (not plus) -
    // the offset literally keeps the tail underneath the viewport floor.
    // Clamp to 0 so the first 3-4 lines just stream in without scrolling.
    const shift = Math.max(0, contentH - viewportH - offset)
    el.style.setProperty('--thinking-shift', `-${shift}px`)
  }, [text, open])
  return (
    <div className={`thinking-block${open ? ' open' : ''}`}>
      <button
        type="button"
        className="thinking-header"
        onClick={onToggle}
        aria-expanded={open}
      >
        <span className="thinking-arrow">{open ? 'v' : '>'}</span>
        <span className="thinking-label">
          {streaming ? 'THINKING…' : 'THINKING'}
        </span>
        <span className="thinking-stats">
          {`${tokens} tok / ${chars} chars`}
        </span>
      </button>
      {open && (
        <div className="thinking-viewport" aria-hidden={!streaming ? undefined : true}>
          {/* no trailing caret - the active token line is kept hidden
              below the bottom fade by the trailing-scroll offset, so a
              cursor here would only add noise the user cannot see */}
          <pre ref={bodyRef} className="thinking-body">{text}</pre>
        </div>
      )}
    </div>
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
