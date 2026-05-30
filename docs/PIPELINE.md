# Assignment 2 — flow from user query to SSE response

Two views: **end-to-end** (what the repo actually runs) and **supervisor** (what happens inside multi-agent mode).

---

## 1. End-to-end: `POST /v1/chat` → SSE

```mermaid
flowchart TB
  subgraph Client["Client"]
    UQ["User: query + session_id + user_context + collaborative"]
  end

  subgraph HTTP["FastAPI — src/api/routes.py"]
    R["POST /v1/chat"]
    H["GET /healthz"]
    Dump["user_context.model_dump → dict"]
    LLM0["get_llm_client or None if LLMError"]
    PQ["process_query async generator"]
    SR["StreamingResponse + stream_events"]
  end

  subgraph SSE["src/api/sse.py"]
    E2W["event_to_sse: meta / token / structured / error / done"]
  end

  UQ --> R --> Dump --> LLM0 --> PQ
  PQ --> SR --> E2W --> OUT["SSE to client curl or browser"]

  subgraph Pipe["src/pipeline.py — process_query"]
    M0["meta received + request_id + session_id"]
    SAFE["safety.check — regex local, no LLM"]
    SB{"blocked?"}
    SG["data + structured safety_guard + done blocked"]
    SESS["get_session_store + get session_id"]
    MCP["attach_mcp_servers_to_context — catalog on user_ctx"]
    CC["update_context_cache slim positions profile"]
    HY["hydrate_user_context from context_cache"]
    DUP{"duplicate query in 180s same text as last user?"}
    DC["reuse prior assistant or stub message — done agent cache"]
    AU["append_turn user"]
    CH["conversation_history = state.history_for_llm"]
    CL["classify — LLM or heuristic + merge_task_decomposition"]
    CR{"chat recap phrasing?"}
    GQ["force agent general_query"]
    META1["meta: classified"]
    CO["update_carryover last_intent + last_tickers"]
    OP["orchestration_profile from task_decomposition"]
    UC{"use_collab = collaborative or MULTIAGENT_ENABLED and eligible and not recap"}
    SK["meta: orchestration collaborative skipped reason"]
    SP["sparse_profile + collaboration_rounds_effective"]
    BR{"use_collab?"}
    SUP["run_collaborative_supervisor"]
    AG["get_agent + agent.run streaming"]
    BUF["buffer data deltas + structured"]
    AT["append_turn assistant"]
    FL{"use_collab?"}
    FS["flush_session — persist discussion_log meta"]
    META2["meta: complete + done"]
  end

  OUT --> UQ

  PQ --> M0
  M0 --> SAFE --> SB
  SB -->|yes| SG
  SB -->|no| SESS --> MCP --> CC --> HY --> DUP
  DUP -->|yes| DC
  DUP -->|no| AU --> CH --> CL
  CL --> CR
  CR -->|yes| GQ
  CR -->|no| META1
  GQ --> META1
  META1 --> CO --> OP --> UC
  UC -->|requested but off| SK
  UC --> SP
  SK --> SP
  SP --> BR
  BR -->|yes| SUP
  BR -->|no| AG
  SUP --> BUF
  AG --> BUF
  BUF --> AT --> FL
  FL -->|yes| FS
  FL -->|no| META2
  FS --> META2

  subgraph Store["src/session.py"]
    ST["SessionState: turns discussion_log orchestrator_meta context_cache"]
    FB["FileBackedSessionStore when APP_ENV not test and SESSION_MEMORY_DIR set"]
  end

  SESS --- Store
  CC --- Store
  AU --- Store
  AT --- Store
  FS --- Store
```

---

## 2. Collaboration gate (how `use_collab` is decided)

```mermaid
flowchart TD
  RC{"Chat recap style query?"}
  REQ{"collaboration_requested collaborative OR MULTIAGENT_ENABLED"}
  ELIG{"agent_panel_eligible portfolio_health risk_assessment OR tax OR retirement OR team_discussion OR macro strategy path"}
  UC["use_collab = REQ AND ELIG AND NOT recap"]

  RC -->|yes| OFF1["use_collab false recap_thread_query"]
  RC -->|no| REQ
  REQ -->|no| OFF2["use_collab false"]
  REQ -->|yes| ELIG
  ELIG -->|no| OFF3["use_collab false intent_not_eligible + meta skip"]
  ELIG -->|yes| UC
```

---

## 3. Inside `run_collaborative_supervisor` (profiles)

```mermaid
flowchart TB
  START["run_collaborative_supervisor"]
  CLR["state.discussion_log.clear — fresh audit trail"]
  TAIL["conversation tail capped for prompts"]
  META["state.orchestrator_meta + meta collaborative_start"]

  START --> CLR --> TAIL --> META --> PROF{"orchestration_profile"}

  PROF -->|tax_market_synthesis| TAX["portfolio → tax_math → market → synthesis"]
  PROF -->|retirement_planning| RET["planner → projection → scenario → tax_account → synthesis deterministic + LLM where wired"]
  PROF -->|agent_team_discussion| TEAM["team_planner.plan_discussion_team → registry or LLM discussion cycles ×2 → chair transcript"]
  PROF -->|else default LLM panel| PNL["portfolio tools MCP → market → risk → momentum → streaming chair"]

  TAX --> OUT["yield meta data structured + discussion_log"]
  RET --> OUT
  TEAM --> OUT
  PNL --> OUT
```

Tooling note: portfolio and market bootstrap rounds call the **MCP shim** (`invoke_mcp`) and log `_mcp_calls` inside `discussion_log` entries where implemented.

---

## 4. Event types on the wire (after `sse.event_to_sse`)

| Pipeline `type` | SSE `event` name | Role |
|----------------|------------------|------|
| `meta` | `meta` | Progress, routing, orchestration hints |
| `data` | `token` | Narrative delta (`delta`) |
| `structured` | `structured` | JSON payload (agent, blocked, tool summaries, etc.) |
| `error` | `error` | Terminal failure message |
| `done` | `done` | End of request; includes `blocked`, `agent`, etc. |

---

## Key files

| Layer | Path |
|-------|------|
| HTTP + SSE | `src/api/routes.py`, `src/api/sse.py`, `src/api/schemas.py` |
| Orchestration | `src/pipeline.py` |
| Safety | `src/safety.py` |
| Session | `src/session.py` |
| MCP catalog | `src/mcp_integration.py`, `src/mcp_servers/registry.py` |
| Classifier + decomposition | `src/classifier.py`, `src/intent_decompose.py` |
| Multi-agent | `src/orchestration/supervisor.py`, `collaborative_llm_agents.py`, `team_planner.py`, `team_registry_bridge.py` |
| Agents | `src/agents/*`, `src/agents/registry.py` |
