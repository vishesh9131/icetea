import { useEffect, useMemo, useState } from 'react'
import {
  deleteAgent,
  fetchAgents,
  fetchToolCatalog,
  upsertAgent,
  type AgentsList,
  type CustomAgent,
  type ToolDescriptor,
} from '../sseClient'

type Props = {
  onClose: () => void
  // If set, the operator clicked "Run" - the parent will call /v1/chat with
  // agent_override = id and send the given query.
  onRunAgent: (id: string, query: string) => void
}

const TEMPLATE_WEB: CustomAgent = {
  id: 'web_research',
  label: 'Web Research',
  description: 'Search the open web and summarise the findings, citing URLs.',
  system_prompt:
    'You are a meticulous web-research assistant for an investor. '
    + 'You receive a [TOOL_RESULTS] JSON block containing web search hits. '
    + 'Read it carefully, then answer the user in 5-8 short bullets. '
    + 'Cite each fact with its source URL in parentheses. '
    + 'Do NOT invent facts that arent in the search results. '
    + 'If the results are thin, say so honestly.',
  tools: ['web_search'],
  temperature: 0.3,
  max_tokens: 700,
}

const EMPTY_FORM: CustomAgent = {
  id: '',
  label: '',
  description: '',
  system_prompt: '',
  tools: [],
  temperature: 0.3,
  max_tokens: 700,
}

export function AgentBuilder({ onClose, onRunAgent }: Props) {
  const [agents, setAgents] = useState<AgentsList | null>(null)
  const [tools, setTools] = useState<ToolDescriptor[]>([])
  const [editing, setEditing] = useState<CustomAgent>(EMPTY_FORM)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [testQuery, setTestQuery] = useState('')

  // Initial load: agents + tool catalog
  useEffect(() => {
    let stopped = false
    Promise.all([fetchAgents(), fetchToolCatalog()]).then(([a, t]) => {
      if (stopped) return
      setAgents(a)
      setTools(t)
    })
    return () => { stopped = true }
  }, [])

  // ESC closes overlay
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const toolsByGroup = useMemo(() => {
    const m = new Map<string, ToolDescriptor[]>()
    for (const t of tools) {
      const g = t.group || 'general'
      if (!m.has(g)) m.set(g, [])
      m.get(g)!.push(t)
    }
    return m
  }, [tools])

  const refreshAgents = async () => setAgents(await fetchAgents())

  const onSave = async () => {
    setError(null)
    setToast(null)
    if (!editing.id || !editing.label || !editing.system_prompt) {
      setError('id, label and system prompt are required')
      return
    }
    setBusy(true)
    const res = await upsertAgent(editing)
    setBusy(false)
    if (!res.ok) {
      setError(res.error || 'save failed')
      return
    }
    setToast(`saved "${editing.id}"`)
    await refreshAgents()
  }

  const onDelete = async (id: string) => {
    if (!confirm(`Delete custom agent "${id}"?`)) return
    setBusy(true)
    const res = await deleteAgent(id)
    setBusy(false)
    if (!res.ok) {
      setError(res.error || 'delete failed')
      return
    }
    setToast(`deleted "${id}"`)
    if (editing.id === id) setEditing(EMPTY_FORM)
    await refreshAgents()
  }

  const onEdit = (a: CustomAgent) => {
    setEditing({ ...a })
    setError(null)
    setToast(null)
  }

  const onLoadTemplate = () => {
    setEditing({ ...TEMPLATE_WEB })
  }

  const onRun = async () => {
    if (!editing.id) {
      setError('save the agent first, then run it')
      return
    }
    // make sure the latest edits are persisted before we run
    setBusy(true)
    const res = await upsertAgent(editing)
    setBusy(false)
    if (!res.ok) {
      setError(res.error || 'save-before-run failed')
      return
    }
    const q = testQuery.trim() || 'give me a quick overview of latest market news this week'
    onRunAgent(editing.id, q)
    onClose()
  }

  const toggleTool = (id: string) => {
    setEditing((prev) => prev.tools.includes(id)
      ? { ...prev, tools: prev.tools.filter((t) => t !== id) }
      : { ...prev, tools: [...prev.tools, id] })
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal builder" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <span>AGENT BUILDER</span>
          <span className="modal-sub">design + register custom agents · ESC to close</span>
          <button className="modal-close" onClick={onClose} title="close (ESC)">×</button>
        </div>

        <div className="builder-body">
          {/* Left column: lists */}
          <div className="builder-left">
            <div className="builder-section-title">CUSTOM AGENTS</div>
            <div className="builder-list">
              {(!agents || agents.custom.length === 0) && (
                <div className="builder-empty">none yet · click LOAD TEMPLATE</div>
              )}
              {agents?.custom.map((a) => (
                <div
                  key={a.id}
                  className={`builder-list-row${editing.id === a.id ? ' active' : ''}`}
                  onClick={() => onEdit(a)}
                >
                  <span className="builder-list-id">{a.id}</span>
                  <span className="builder-list-label">{a.label}</span>
                  <button
                    className="builder-del"
                    onClick={(e) => { e.stopPropagation(); onDelete(a.id) }}
                    title="DELETE"
                  >×</button>
                </div>
              ))}
            </div>

            <div className="builder-section-title">BUILT-IN AGENTS  <span className="builder-hint">(read-only)</span></div>
            <div className="builder-list builtin">
              {agents?.builtin.map((a) => (
                <div key={a.id} className="builder-list-row builtin">
                  <span className="builder-list-id">{a.id}</span>
                  <span className={`builder-list-impl ${a.implemented ? 'on' : 'off'}`}>
                    {a.implemented ? 'IMPL' : 'STUB'}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Right column: form */}
          <div className="builder-right">
            <div className="builder-row">
              <label>
                <span>ID</span>
                <input
                  value={editing.id}
                  onChange={(e) => setEditing({ ...editing, id: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_') })}
                  placeholder="snake_case_id"
                />
              </label>
              <label>
                <span>LABEL</span>
                <input
                  value={editing.label}
                  onChange={(e) => setEditing({ ...editing, label: e.target.value })}
                  placeholder="Web Research"
                />
              </label>
            </div>
            <label className="builder-row-single">
              <span>DESCRIPTION</span>
              <input
                value={editing.description}
                onChange={(e) => setEditing({ ...editing, description: e.target.value })}
                placeholder="what does this agent do?"
              />
            </label>
            <label className="builder-row-single">
              <span>SYSTEM PROMPT</span>
              <textarea
                value={editing.system_prompt}
                onChange={(e) => setEditing({ ...editing, system_prompt: e.target.value })}
                rows={8}
                placeholder="You are a meticulous research assistant..."
              />
            </label>
            <div className="builder-row">
              <label>
                <span>TEMPERATURE</span>
                <input
                  type="number" step="0.05" min="0" max="2"
                  value={editing.temperature}
                  onChange={(e) => setEditing({ ...editing, temperature: parseFloat(e.target.value || '0') })}
                />
              </label>
              <label>
                <span>MAX TOKENS</span>
                <input
                  type="number" step="32" min="32" max="4000"
                  value={editing.max_tokens}
                  onChange={(e) => setEditing({ ...editing, max_tokens: parseInt(e.target.value || '0', 10) })}
                />
              </label>
            </div>

            <div className="builder-section-title">
              TOOLS (MCP + WEB)  <span className="builder-hint">{editing.tools.length} selected</span>
            </div>
            <div className="builder-tools">
              {Array.from(toolsByGroup.entries()).map(([group, list]) => (
                <div key={group} className="builder-tool-group">
                  <div className="builder-tool-group-name">{group.replace('mcp_', 'mcp · ')}</div>
                  {list.map((t) => (
                    <label key={t.tool_id} className="builder-tool">
                      <input
                        type="checkbox"
                        checked={editing.tools.includes(t.tool_id)}
                        onChange={() => toggleTool(t.tool_id)}
                      />
                      <span className="builder-tool-label">{t.label}</span>
                      <span className="builder-tool-desc">{t.description || '—'}</span>
                    </label>
                  ))}
                </div>
              ))}
            </div>

            {error && <div className="builder-error">{error}</div>}
            {toast && <div className="builder-toast">{toast}</div>}

            <div className="builder-footer">
              <button className="builder-btn" onClick={onLoadTemplate} disabled={busy}>
                LOAD TEMPLATE
              </button>
              <button className="builder-btn" onClick={() => setEditing(EMPTY_FORM)} disabled={busy}>
                NEW
              </button>
              <button className="builder-btn primary" onClick={onSave} disabled={busy}>
                SAVE
              </button>

              <div className="builder-run">
                <input
                  className="builder-run-input"
                  value={testQuery}
                  onChange={(e) => setTestQuery(e.target.value)}
                  placeholder='Test query e.g. "what is the fed up to this week?"'
                />
                <button className="builder-btn primary" onClick={onRun} disabled={busy || !editing.id}>
                  RUN ▶
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
