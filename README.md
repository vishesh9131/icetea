# Icetea

A multi-agent AI co-investor for novice retail traders.

Icetea routes natural-language queries through a synchronous **safety guard**,
an LLM **intent classifier**, and a roster of **specialist agents** (portfolio
health, risk assessment, investment strategy, debate, financial planning,
product recommendation, market research, and more), then streams the
response over Server-Sent Events to a Bloomberg-style **operator terminal**
in the browser.

## Layout

```
.
├── backend/                  FastAPI + agent pipeline + SSE
│   ├── icetea/               the python package
│   │   ├── api/              app.py, routes.py, schemas.py, sse.py
│   │   ├── agents/           portfolio_health, risk_assessment, ... stubs
│   │   ├── orchestration/    collaborative supervisor + toolkits
│   │   ├── mcp_servers/      in-process MCP shim + registry
│   │   ├── classifier.py     LLM-backed intent + entity extraction
│   │   ├── safety.py         deterministic pre-LLM safety guard
│   │   ├── pipeline.py       safety → classifier → agent → stream
│   │   ├── session.py        file-backed session memory
│   │   ├── llm.py            OpenAI / vLLM unified client
│   │   ├── market_data.py    yfinance wrapper (cached, fault-tolerant)
│   │   ├── config.py
│   │   ├── intent_decompose.py
│   │   └── mcp_integration.py
│   ├── mcp_servers/          standalone MCP server scripts (FastMCP)
│   ├── tests/                pytest suite (117 tests)
│   ├── scripts/              dev scripts + harness/ (79 e2e scenarios)
│   ├── fixtures/             sample users + conversations + queries
│   ├── pytest.ini
│   ├── requirements.txt
│   ├── run_dev.sh            one-line uvicorn launcher
│   └── README.md             backend-specific docs
├── frontend/                 React + Vite + TS terminal UI
│   ├── src/                  components, sse client, themes, profiles
│   ├── package.json
│   └── README.md             frontend-specific docs
├── docs/                     assignment + design + legacy README
│   ├── ASSIGNMENT.md
│   ├── PIPELINE.md
│   └── README_LEGACY.md
├── assets/                   benchmark images referenced from docs
├── Makefile                  dev / test / harness / build / clean
└── .env.example
```

## Quick start

Two terminals — one for the backend, one for the frontend.

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env .env  # or edit .env directly
./run_dev.sh
# → http://127.0.0.1:8000  (healthz, /v1/chat)
```

`run_dev.sh` just `exec`s:

```bash
PYTHONPATH=. uvicorn icetea.api.app:app --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

Backend at `:8000` is the default; override with
`VITE_BACKEND_BASE=https://my-host npm run dev`.

### One-command dev

```bash
make dev    # starts backend + frontend in parallel
make test   # backend pytest
make harness # full 79-scenario end-to-end run
```

## What ships in this build

- **Safety guard** — synchronous regex/heuristic layer that blocks insider
  trading, guaranteed-returns claims, market manipulation, money laundering,
  reckless advice, sanctions evasion, fraud, prompt-injection, and out-of-scope
  asks. Has dedicated refusal copy per category.
- **Intent classifier** — LLM call (vLLM-compatible OR OpenAI) returning
  intent + ticker entities + confidence. Falls back to general_query on
  parse failure.
- **Agents** — 11 specialists:
  - `portfolio_health` (real, with live market data via yfinance + benchmark alpha)
  - `risk_assessment` (real, scenario stress + concentration + currency exposure + beta proxy)
  - `investment_strategy` (real, multi-step plan with feasibility checks)
  - `investment_debate` (real, parallel bull / bear panels)
  - `financial_planning` (real, retirement / house / college planning)
  - `product_recommendation` (real, ETF/fund matching with web tools)
  - `general_query` (LLM-narrated fallback)
  - `portfolio_query` (deterministic answer from cached book)
  - stubs (`market_research`, `predictive_analysis`, `financial_calculator`,
    `customer_support`) — context-aware "not implemented" with carryover ticker
- **Collaborative supervisor** — multi-round panel (portfolio + market + planner)
  with tool calls into the MCP shim, kicked in for macro / multi-step requests.
- **Session memory** — file-backed, carryover ticker, multi-turn pronoun
  resolution, cache short-circuit for exact duplicate queries.
- **HTTP layer** — FastAPI, SSE over POST, CORS scoped to the Vite ports.
- **Frontend** — 4-pane Bloomberg-style terminal, 5 selectable themes
  (Bloomberg Amber / Icetea Teal / CRT Green / Ice Blue / Paperwhite),
  editable holdings, agent trace pane, F-key shortcuts, status bar.

## Tests

```bash
make test      # 117 unit tests
make harness   # 79 e2e scenarios, sequential
make harness-c # 79 e2e scenarios, --concurrency 4
```

All scenarios pass against the vLLM tunnel at `https://vllm.corerec.online/v1`
under the `Jackrong/Qwopus3.5-27B-v3` model with the default `.env`.

## Configuration

Copy `.env.example` to `backend/.env` and edit. Key settings:

| Variable                       | Default               | Notes                              |
| ------------------------------ | --------------------- | ---------------------------------- |
| `LLM_PROVIDER`                 | `vllm`                | `openai` or `vllm`                 |
| `VLLM_BASE_URL`                | `https://vllm.corerec.online/v1` | OpenAI-compatible vLLM        |
| `VLLM_MODEL`                   | `Jackrong/Qwopus3.5-27B-v3` |                              |
| `OPENAI_API_KEY`               | —                     | only if `LLM_PROVIDER=openai`      |
| `LLM_PER_CALL_TIMEOUT_S`       | `60.0`                | per LLM call                       |
| `REQUEST_TIMEOUT_S`            | `180`                 | full pipeline wall                 |
| `ALLOWED_ORIGINS`              | localhost:5173 + 4173 | CORS for the terminal              |
| `APP_ENV`                      | `development`         | `production` for live deploys      |

## License

MIT.
