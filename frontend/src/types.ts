// Mirror of src/api/schemas.py — kept thin on purpose so the wire shape
// is exactly what the FastAPI app accepts. If the backend evolves, this is
// the file that needs the matching tweak.

export type Position = {
  ticker: string
  exchange?: string | null
  quantity: number
  avg_cost?: number
  currency?: string
  purchased_at?: string | null
}

export type UserContext = {
  user_id: string
  name?: string | null
  age?: number | null
  country?: string | null
  base_currency?: string
  risk_profile?: string | null
  kyc?: Record<string, unknown> | null
  positions: Position[]
  preferences?: Record<string, unknown>
}

export type ChatRequest = {
  query: string
  session_id: string
  user_context?: UserContext | null
  collaborative?: boolean
  // When set, bypass the classifier and dispatch directly to this agent.
  // The Agent Builder UI uses this to run a freshly-defined custom agent
  // without retraining the intent classifier.
  agent_override?: string | null
}

// ---- SSE event envelope as decoded on the client. ---------------------

export type SseEvent =
  | { kind: 'token'; delta: string }
  | { kind: 'structured'; payload: Record<string, unknown> }
  | { kind: 'meta'; payload: Record<string, unknown> }
  | { kind: 'error'; payload: Record<string, unknown> }
  | { kind: 'done'; payload: Record<string, unknown> }
  | { kind: 'other'; name: string; payload: Record<string, unknown> }

// ---- UI-side message log ----------------------------------------------

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant' | 'system' | 'error'
  text: string
  ts: number
  agent?: string | null
  collaborative?: boolean
  structured?: Record<string, unknown> | null
  streaming?: boolean
  latencyMs?: number
  blocked?: boolean
  blockCategory?: string
  // most recent collaborative round/agent surfaced in the bubble while we wait
  // for token output. Cleared on the first real token from the LLM.
  progress?: { stage: string; round?: number; agent?: string } | null
}

export type TraceEntry = {
  id: string
  ts: number
  kind: 'token' | 'meta' | 'structured' | 'error' | 'done' | 'classif' | 'guard' | 'session' | 'other'
  label: string
  body: string
}
