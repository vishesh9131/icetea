import { useEffect, useMemo, useRef, useState } from 'react'
import { CATEGORIES, PROMPT_TEMPLATES, type PromptTemplate } from '../promptTemplates'

type Props = {
  open: boolean
  onClose: () => void
  // called when operator picks a template:
  //   sendNow=true  -> fire the query straight at the pipeline
  //   sendNow=false -> just drop it into the cmdbar input for editing
  onPick: (t: PromptTemplate, sendNow: boolean) => void
}

// Little popover anchored to the right side of the command bar.
// Pops upward because the cmdbar lives near the bottom of the screen.
export function PromptPalette({ open, onClose, onPick }: Props) {
  const [filter, setFilter] = useState('')
  const [category, setCategory] = useState<string>('ALL')
  const [activeIdx, setActiveIdx] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  // each open is a fresh palette session - reset filters + focus the search
  useEffect(() => {
    if (!open) return
    setFilter('')
    setActiveIdx(0)
    const id = window.setTimeout(() => inputRef.current?.focus(), 0)
    return () => window.clearTimeout(id)
  }, [open])

  const filtered = useMemo(() => {
    const f = filter.trim().toLowerCase()
    return PROMPT_TEMPLATES.filter((t) => {
      if (category !== 'ALL' && t.category !== category) return false
      if (!f) return true
      return (
        t.title.toLowerCase().includes(f)
        || t.prompt.toLowerCase().includes(f)
        || t.category.toLowerCase().includes(f)
      )
    })
  }, [filter, category])

  // clamp the active index whenever the filtered list shrinks
  useEffect(() => {
    if (activeIdx >= filtered.length) setActiveIdx(Math.max(0, filtered.length - 1))
  }, [filtered.length, activeIdx])

  // keep the active row in view as we arrow through
  useEffect(() => {
    if (!open) return
    const el = listRef.current?.querySelector<HTMLElement>(`[data-idx="${activeIdx}"]`)
    if (el) el.scrollIntoView({ block: 'nearest' })
  }, [activeIdx, open])

  if (!open) return null

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx((i) => Math.min(filtered.length - 1, i + 1))
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx((i) => Math.max(0, i - 1))
      return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      const t = filtered[activeIdx]
      if (!t) return
      // shift/cmd+enter ships it immediately, plain enter just fills the cmdbar
      const sendNow = e.shiftKey || e.metaKey || e.ctrlKey
      onPick(t, sendNow)
      onClose()
      return
    }
    if (e.key === 'Tab') {
      // tab cycles category filter
      e.preventDefault()
      const cats = ['ALL', ...CATEGORIES]
      const idx = cats.indexOf(category)
      const next = cats[(idx + (e.shiftKey ? -1 : 1) + cats.length) % cats.length]
      setCategory(next)
    }
  }

  return (
    <>
      {/* click-outside / esc backdrop */}
      <div className="palette-backdrop" onClick={onClose} />
      <div
        className="palette"
        role="dialog"
        aria-label="Prompt templates"
        onKeyDown={onKeyDown}
      >
        <div className="palette-head">
          <span className="palette-title">PROMPT TEMPLATES</span>
          <span className="palette-hint">
            <kbd>Enter</kbd> insert · <kbd>Shift+Enter</kbd> insert + send · <kbd>Tab</kbd> next category · <kbd>Esc</kbd> close
          </span>
        </div>
        <div className="palette-tabs">
          {['ALL', ...CATEGORIES].map((c) => (
            <button
              key={c}
              className={`palette-tab${category === c ? ' on' : ''}`}
              onClick={() => { setCategory(c); inputRef.current?.focus() }}
            >
              {c}
            </button>
          ))}
        </div>
        <div className="palette-search">
          <span className="palette-prompt">/</span>
          <input
            ref={inputRef}
            className="palette-input"
            placeholder="filter templates...  e.g. nvda, hedge, retirement"
            value={filter}
            onChange={(e) => { setFilter(e.target.value); setActiveIdx(0) }}
          />
        </div>
        <div className="palette-list" ref={listRef}>
          {filtered.length === 0 && (
            <div className="palette-empty">no template matches "{filter}"</div>
          )}
          {filtered.map((t, i) => (
            <div
              key={t.id}
              data-idx={i}
              className={`palette-row${i === activeIdx ? ' active' : ''}`}
              onMouseEnter={() => setActiveIdx(i)}
              onClick={() => { onPick(t, false); onClose() }}
            >
              <div className="palette-row-head">
                <span className="palette-row-cat">{t.category}</span>
                <span className="palette-row-title">{t.title}</span>
                {t.agent_override && (
                  <span className="palette-row-override">→ {t.agent_override}</span>
                )}
              </div>
              <div className="palette-row-prompt">{t.prompt}</div>
            </div>
          ))}
        </div>
        <div className="palette-foot">
          <span className="palette-count">{filtered.length} / {PROMPT_TEMPLATES.length}</span>
          <button
            className="palette-send"
            disabled={!filtered[activeIdx]}
            onClick={() => {
              const t = filtered[activeIdx]
              if (!t) return
              onPick(t, true)
              onClose()
            }}
            title="insert + send (Shift+Enter)"
          >RUN ▶</button>
        </div>
      </div>
    </>
  )
}
