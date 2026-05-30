import { useEffect, useRef, useState } from 'react'

export type CommandAction =
  | { kind: 'send'; text: string }
  | { kind: 'cancel' }
  | { kind: 'clear' }
  | { kind: 'toggle-collab' }
  | { kind: 'help' }

type Props = {
  busy: boolean
  collaborative: boolean
  onAction: (a: CommandAction) => void
  onOpenBuilder?: () => void
}

// Each slot has an F-key (great on Windows/Linux + Macs with
// "Use F1, F2 as standard function keys" enabled) AND a Control+digit
// alias for the rest of us. On macOS the top-row keys default to
// brightness/volume so plain F1 doesn't reach the browser; Ctrl+1..0
// always does, and it doesnt collide with the Cmd+1..4 dock focus keys.
type SlotDef = { fkey: string; ctrlKey: string; label: string; action: () => CommandAction }

const SLOTS: SlotDef[] = [
  { fkey: 'F1',  ctrlKey: '1', label: 'CHAT',   action: () => ({ kind: 'send', text: 'how is my portfolio doing?' }) },
  { fkey: 'F2',  ctrlKey: '2', label: 'PORT',   action: () => ({ kind: 'send', text: 'show me my holdings' }) },
  { fkey: 'F3',  ctrlKey: '3', label: 'RISK',   action: () => ({ kind: 'send', text: 'stress test my portfolio if the market drops 30% next quarter' }) },
  { fkey: 'F4',  ctrlKey: '4', label: 'MR',     action: () => ({ kind: 'send', text: 'how is nvda doing this week?' }) },
  { fkey: 'F5',  ctrlKey: '5', label: 'STRAT',  action: () => ({ kind: 'send', text: 'should i sell half of nvda?' }) },
  { fkey: 'F6',  ctrlKey: '6', label: 'DEBATE', action: () => ({ kind: 'send', text: 'give me the bull case AND bear case on microsoft for 3 years' }) },
  { fkey: 'F7',  ctrlKey: '7', label: 'PLAN',   action: () => ({ kind: 'send', text: 'how do i plan retirement at 60 if i save 2000 a month' }) },
  { fkey: 'F8',  ctrlKey: '8', label: 'HELP',   action: () => ({ kind: 'help' }) },
  { fkey: 'F9',  ctrlKey: '9', label: 'CLEAR',  action: () => ({ kind: 'clear' }) },
  { fkey: 'F10', ctrlKey: '0', label: 'COLLAB', action: () => ({ kind: 'toggle-collab' }) },
]

const FKEY_MAP: Record<string, () => CommandAction> = Object.fromEntries(
  SLOTS.map((s) => [s.fkey, s.action]),
)
const CTRL_KEY_MAP: Record<string, () => CommandAction> = Object.fromEntries(
  SLOTS.map((s) => [s.ctrlKey, s.action]),
)

export function CommandBar({ busy, collaborative, onAction, onOpenBuilder }: Props) {
  const [text, setText] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  // global F-keys + ENTER while focused elsewhere -> still send.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      const isInput =
        target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT')
      if (FKEY_MAP[e.key]) {
        e.preventDefault()
        const a = FKEY_MAP[e.key]()
        if (a.kind === 'send') setText(a.text)
        onAction(a)
        inputRef.current?.focus()
        return
      }
      // Mac-friendly Ctrl+digit alias (NOT Cmd — Cmd is the dock focus prefix).
      // Cmd+1..4 already focuses dock tiles, so we cant overload it here.
      if (e.ctrlKey && !e.metaKey && !e.shiftKey && !e.altKey && CTRL_KEY_MAP[e.key]) {
        e.preventDefault()
        const a = CTRL_KEY_MAP[e.key]()
        if (a.kind === 'send') setText(a.text)
        onAction(a)
        inputRef.current?.focus()
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        onAction({ kind: 'cancel' })
        return
      }
      if (e.key === '/' && !isInput) {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onAction])

  const submit = () => {
    const t = text.trim()
    if (!t) return
    onAction({ kind: 'send', text: t })
    setText('')
  }

  return (
    <div className="cmdbar">
      <span className="prompt">ICE&gt;</span>
      <input
        ref={inputRef}
        className="input"
        placeholder='Enter query  ·  e.g. "how is my portfolio?"  ·  press / to focus  ·  ESC to cancel'
        value={text}
        autoFocus
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            submit()
          }
        }}
      />
      <div className="actions">
        {SLOTS.map((s) => (
          <span
            key={s.fkey}
            className="chip"
            title={`${s.fkey}  or  Ctrl+${s.ctrlKey}  ·  ${s.label}`}
            onClick={() => {
              const a = s.action()
              if (a.kind === 'send') setText(a.text)
              onAction(a)
              inputRef.current?.focus()
            }}
            style={{ cursor: 'pointer' }}
          >
            <span className="fg-amber-bright">{s.fkey}</span>
            <span className="key-alt">·^{s.ctrlKey}</span>&nbsp;{s.label}
          </span>
        ))}
        <span className={`chip ${collaborative ? 'on' : ''}`} onClick={() => onAction({ kind: 'toggle-collab' })} style={{ cursor: 'pointer' }} title="F10 / Ctrl+0  ·  COLLABORATIVE PIPELINE">
          COLLAB {collaborative ? 'ON' : 'OFF'}
        </span>
        {onOpenBuilder && (
          <span
            className="chip"
            onClick={onOpenBuilder}
            style={{ cursor: 'pointer' }}
            title="Ctrl+B  ·  AGENT BUILDER (build/edit/run custom agents)"
          >
            <span className="fg-amber-bright">^B</span> BUILD
          </span>
        )}
        {busy ? (
          <button className="btn" onClick={() => onAction({ kind: 'cancel' })} title="ESC">CANCEL</button>
        ) : (
          <button className="btn" onClick={submit} disabled={!text.trim()}>SEND</button>
        )}
      </div>
    </div>
  )
}
