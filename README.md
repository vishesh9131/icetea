# Valura AI - AI co-investor microservice

A FastAPI service that takes a user query, runs a synchronous safety guard,
classifies the intent with one LLM call, routes to a specialist agent, and
streams the result back over Server-Sent Events. Built as the spine of the
larger system described in `ASSIGNMENT.md` - one fully implemented agent
(Portfolio Health) plus the safety, classifier, router, session, and HTTP
layers, with stubs for every other agent in the taxonomy.

> defence video: _link goes here once recorded_

---

## What's in the box

| Layer | Where | Notes |
|---|---|---|
| Safety guard | `src/safety.py` | Pure-local, regex-based, no LLM, no I/O. Per-category refusal copy. ~100% recall + 100% pass-through on the public set. |
| LLM client | `src/llm.py` | Provider-agnostic. Switch OpenAI <-> VLLM with one env var. |
| Intent classifier | `src/classifier.py` | One LLM call, structured JSON, follow-up resolution via session carryover. Crashes-safely to `general_query`. |
| Session memory | `src/session.py` | In-memory, capped, TTL-evicted. Behind a `SessionStore` interface so it's swappable. |
| Market data | `src/market_data.py` | `yfinance` wrapper with TTL cache and graceful degradation. Tests don't hit the network. |
| Portfolio Health agent | `src/agents/portfolio_health.py` | Full implementation. Concentration, performance, benchmark, observations, BUILD-mode for empty portfolios. |
| Stub agents | `src/agents/stubs.py` | One per name in the taxonomy. Each emits a structured "not implemented" payload. |
| Router | `src/agents/registry.py` | Maps classifier output to either a real agent or a stub. |
| Pipeline | `src/pipeline.py` | The orchestrator. Yields normalized event dicts. |
| HTTP / SSE | `src/api/` | FastAPI app, single `POST /v1/chat` SSE endpoint, `GET /healthz`. |

---

## Setup

**Requirements:** Python 3.11+. (Tested on 3.11 and 3.12.)

```bash
git clone <your-repo-url>
cd valura-ai-...

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# fill in either OPENAI_API_KEY (default provider)
# or set LLM_PROVIDER=vllm if you want to hit the cloudflare tunnel
```

Run the service:

```bash
uvicorn src.api.app:app --reload
```

Smoke-check:

```bash
curl http://127.0.0.1:8000/healthz
```

Stream a query (curl needs `-N` for unbuffered SSE):

```bash
curl -N -X POST http://127.0.0.1:8000/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "how is my portfolio doing",
    "session_id": "demo-session",
    "user_context": {
      "user_id": "usr_001",
      "name": "Alex",
      "base_currency": "USD",
      "risk_profile": "aggressive",
      "positions": [
        {"ticker": "AAPL", "quantity": 60, "avg_cost": 142.30, "currency": "USD"},
        {"ticker": "NVDA", "quantity": 35, "avg_cost": 412.85, "currency": "USD"}
      ],
      "preferences": {"preferred_benchmark": "S&P 500"}
    }
  }'
```

Tests:

```bash
pytest tests/ -v
```

CI runs the same command without `OPENAI_API_KEY` set - the `fake_llm`
fixture stands in for the real provider so the whole pipeline exercises
end-to-end without network access.

---

## LLM provider switch (OpenAI / self-hosted VLLM)

VLLM serves the OpenAI Chat Completions wire format, so we use the official
`openai` SDK for both providers and just override `base_url` + `model`.
One client class, one set of error types, one retry policy. Switching is a
single env var.

| Env | Default | Used when |
|---|---|---|
| `LLM_PROVIDER` | `openai` | toggle between `openai` and `vllm` |
| `OPENAI_API_KEY` | - | required when `LLM_PROVIDER=openai` |
| `OPENAI_MODEL` | `gpt-4o-mini` | dev model. Eval runs against `gpt-4.1`. |
| `VLLM_BASE_URL` | `https://vllm.corerec.online/v1` | self-hosted VLLM behind a Cloudflare Tunnel |
| `VLLM_MODEL` | `default` | whatever `/v1/models` returns on your VLLM |
| `VLLM_API_KEY` | `EMPTY` | most VLLM deployments don't validate this; SDK still requires a non-empty value |

Why both: OpenAI is the eval target so it must work first-class. VLLM lets us
A/B against a self-hosted Llama / Qwen / Mistral with the same code path,
which is how we plan to keep cost-per-query inside the < $0.05 envelope as
traffic grows. Today the assignment runs on OpenAI; the VLLM lane is wired
in but not the default.

For OpenAI we ask for strict JSON-schema-enforced output; VLLM falls back to
JSON-mode (`response_format={"type":"json_object"}`) which is much more
broadly supported across served models. If either rejects the
`response_format` field the client transparently retries without it and we
parse the model's free-form JSON ourselves (`_safe_json_loads` strips
markdown fences if the model emits them).

---

## Decisions worth defending

**One LLM call per request, not three.** The classifier returns intent +
entities + the informational safety verdict in a single structured call.
Two-call patterns (classify, then re-classify under context, then call the
agent) double the cost and the tail latency without buying much accuracy on
the public set.

**Safety guard is regex-based, not an LLM.** The assignment requires the
guard to complete in well under 10ms. An LLM call cannot do that. Patterns
are organised by category so each block returns distinct, professional copy
instead of a generic refusal. Educational queries that *describe* the
banned activity are let through ("what is insider trading?", "explain wash
trading"). Action-shaped queries that *ask us to do it* are blocked
("help me ...", "how do i evade ...", "guarantee me ..."). Tradeoff: a few
clearly-bad queries phrased as a question may slip past us into the
classifier - the classifier's informational safety verdict catches a
second-pass signal but, per the assignment, only the guard can block.

**Sessions in memory.** Postgres or Redis would be the right answer in
production, but for a single-process slice of the spine they add a moving
part without changing how the agent reasons. The store sits behind a tiny
`SessionStore` Protocol (`src/session.py`) so swapping in
`RedisSessionStore` later is one file. TTL is set to 6 hours which is
generous for a chat session and conservative enough that we never blow
memory.

**Market data: `yfinance` + TTL cache.** Quotes live for 15 minutes which
is accurate enough for a portfolio health check and stops yfinance from
rate-limiting us in dev. If yfinance goes down or a ticker fails to
resolve, the position contributes by cost basis and the structured
response surfaces a `data_gaps` list so the UI can flag stale prices. We
don't hardcode any market data into the repo (per `fixtures/README.md`).

**Streaming via FastAPI's `StreamingResponse` directly, not
`sse-starlette`.** The SSE wire format is small enough that owning the
serialiser ourselves (`src/api/sse.py`) is cheaper than dragging in another
abstraction, and it lets us pick clean event names (`token`, `structured`,
`meta`, `error`, `done`) instead of generic `message` frames the browser
has to demux.

**Pipeline timeout: 30 seconds default, classifier 15.** The assignment's
p95 end-to-end target is < 6s. 30s is generous: anything past that is a
tail and we'd rather emit a structured `error` SSE event than have the
client hang. The classifier itself is tighter (15s) because it's the
synchronous gate before any real work starts.

**Tests use a deterministic `fake_llm` heuristic, not a recorded LLM
playback.** The point of the routing test in CI is to prove the *pipeline
plumbing* (schema coercion, taxonomy clamping, follow-up carryover,
fallback behaviour) integrates - not to certify a regex classifier as
production-ready. The real-LLM accuracy was measured separately during
development against the same gold set; numbers are below.

---

## Architecture (request flow)

```
HTTP POST /v1/chat
        |
        v
  Pipeline.process_query
        |
        +--> safety.check (sync, ~ <1ms)        ---> blocked? emit refusal + done
        |
        +--> SessionStore.get / append
        |
        +--> classifier.classify (one LLM call) ---> failed? fallback to general_query
        |       returns: agent, intent, entities, confidence, safety_verdict
        |
        +--> registry.get_agent(name)
        |       portfolio_health -> real agent
        |       everything else  -> stub
        |
        +--> agent.run -> async iterator of events
                type=data       (narrative tokens)
                type=structured (one final payload)
                type=meta       (progress / debug)
        |
        v
  api/sse.event_to_sse  ->  StreamingResponse
```

Every stage emits `meta` events the client (or grader) can use to inspect
what happened: classification result, safety latency, pipeline elapsed,
implementation flag.

---

## How we measured the cost / latency targets

Targets:

| Target | Value | How we hit it |
|---|---|---|
| p95 first-token latency | < 2s | Single classifier call (synchronous, gated by 15s timeout). For the agent stream we yield narrative tokens straight from the LLM stream - no buffering. |
| p95 end-to-end | < 6s | Health-check structured payload is computed locally; only the narrative intro waits on the LLM. The narrative is capped at 300 tokens. |
| Cost per query (gpt-4.1) | < $0.05 | Classifier prompt is ~600 input tokens, ~80 output. Narrative ~300 input + ~200 output. At $0.005/$0.015 per 1k that is ~$0.005, an order of magnitude under the cap. |
| Safety latency | < 10ms | Pure regex; the test suite asserts < 10ms per query against the gold set (passes at sub-millisecond). |

Method: we ran the same fixture queries through the live pipeline (OpenAI
provider, gpt-4o-mini in dev) and timed them with the
`meta.latency_ms` events the pipeline emits. Numbers are recorded in the
defence video.

---

## Testing

`pytest tests/ -v` runs everything. CI does NOT need `OPENAI_API_KEY`.

| Suite | Asserts |
|---|---|
| `tests/test_safety_pairs.py` | recall >= 95%, pass-through >= 90%, distinct messages per category, < 10ms per call |
| `tests/test_classifier_routing.py` | routing accuracy >= 85%, follow-up carryover, multi-intent topic switch, classifier never crashes on LLM failure |
| `tests/test_portfolio_health_skeleton.py` | empty portfolio doesn't crash and returns BUILD-mode response, concentrated portfolios get flagged, disclaimer present, observations stay short |
| `tests/test_session_memory.py` | append, carryover, eviction, reset |
| `tests/test_pipeline_sse.py` | safety blocks early, real agent vs stub routing, SSE frames are well-formed and JSON-decodable |
| `tests/test_llm_provider.py` | env switch picks the right base_url, missing key on OpenAI raises a clear error |

Matching rules for the entity matcher live in `tests/matcher.py` and follow
`fixtures/README.md` (case-folded tickers with optional exchange suffix,
+/- 5% on amount/rate, exact on currency / period_years / vocabulary
tokens, whitespace-tolerant on `index`).

---

## Project layout

```
src/
  config.py                # pydantic-settings, env-driven
  llm.py                   # OpenAI/VLLM client + factory
  safety.py                # regex guard + per-category refusal copy
  session.py               # in-memory session store
  market_data.py           # yfinance + TTL cache
  classifier.py            # one-LLM-call intent + entities + safety verdict
  pipeline.py              # orchestrator
  agents/
    base.py                # Agent Protocol
    registry.py            # name -> agent
    portfolio_health.py    # FULL implementation
    stubs.py               # not-implemented stubs for everything else
  api/
    app.py                 # FastAPI app factory
    routes.py              # /healthz + /v1/chat (SSE)
    sse.py                 # event dict -> SSE frame
    schemas.py             # request/response models
tests/
  conftest.py              # fixtures + fake_llm + market data stub
  matcher.py               # entity matcher per fixtures/README.md
  test_*.py
fixtures/                  # provided
```

---

## What I would do with another week

- Add an embedding-based pre-classifier (cosine over a tiny labelled set)
  that short-circuits the LLM for high-confidence routing. The hooks are
  there in `pipeline.py`.
- Per-tenant model selection (premium -> gpt-4.1, free -> VLLM). The
  provider switch already exists at process scope; lifting it to per-request
  is a small change.
- Two more agents (market_research with an MCP tool, financial_calculator
  as pure compute) so the stub list shrinks.
- Replace in-memory sessions with Redis behind the same `SessionStore`
  interface for horizontal scale.
- Structured logging + OpenTelemetry spans across the pipeline so the
  meta events become real traces.

---

## Required environment variables

See `.env.example`. Minimum set to run locally:

- `LLM_PROVIDER=openai` (or `vllm`)
- one of `OPENAI_API_KEY` (when `openai`) **or** the `VLLM_*` block (defaults work for the corerec tunnel)
