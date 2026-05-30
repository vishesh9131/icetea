# Icetea Terminal — Bloomberg-style frontend

A four-pane operator console for the Icetea multi-agent backend.
Amber on black, monospace, no rounded corners, no animations except a
blinking cursor and the headline ticker. Function keys map to canned
queries so you can demo every agent with one keystroke.

## What you get

- **HEADER**       session id, model, provider, env, NET status, UTC clock
- **TICKER**       scrolling sample market band
- **CHAT**         streamed agent narrative, color-coded per role, structured
                   payload togglable per turn, blinking cursor while streaming
- **PORTFOLIO**    editable holdings table + profile presets
                   (empty / concentrated / global / penny / bonds)
- **PROFILE**      static read-only summary of the active user context
- **AGENT TRACE**  live event log — every meta, classif, structured, error
                   the backend emits, with millisecond timestamps
- **COMMAND BAR**  prompt with F-key shortcuts, COLLAB toggle, cancel
- **STATUS BAR**   NET, PIPE, last agent, latency, blocked count, COLLAB, clock

## Function keys

| Key  | Action  | Sends                                                  |
| ---- | ------- | ------------------------------------------------------ |
| F1   | CHAT    | "how is my portfolio doing?"                           |
| F2   | PORT    | "show me my holdings"                                  |
| F3   | RISK    | "stress test my portfolio if the market drops 30%..."  |
| F4   | MR      | "how is nvda doing this week?"                         |
| F5   | STRAT   | "should i sell half of nvda?"                          |
| F6   | DEBATE  | "give me the bull case AND bear case on microsoft..." |
| F7   | PLAN    | "how do i plan retirement at 60 if i save 2000/mo"     |
| F8   | HELP    | print this list in the chat pane                       |
| F9   | CLEAR   | wipe transcript and start a new session id             |
| F10  | COLLAB  | toggle the collaborative multi-agent pipeline          |
| F12  | THEME   | cycle through the 5 themes                             |
| ESC  | CANCEL  | abort the in-flight SSE stream                         |
| /    | FOCUS   | jump the cursor to the command bar                     |

## Themes

Five palettes ship out of the box (CSS-variable swaps under
`html[data-theme="..."]`). Pick from the THEME select in the status bar or
mash **F12** to cycle. Choice persists in `localStorage` under
`icetea.theme`.

| Theme   | Vibe                                |
| ------- | ----------------------------------- |
| amber   | Classic Bloomberg amber on black    |
| teal    | Icetea brand — teal/cyan on midnight|
| crt     | Phosphor green CRT terminal         |
| ice     | Cold ice-blue glass                 |
| paper   | Inverted paperwhite (high contrast) |

## Run

Backend first (from repo root):

```bash
make backend
# or, manually:
cd backend && PYTHONPATH=. uvicorn icetea.api.app:app --host 127.0.0.1 --port 8000
```

Frontend (separate shell):

```bash
make frontend
# or, manually:
cd frontend && npm install && npm run dev
```

Open `http://localhost:5173`. The terminal probes `/healthz` every 10s; if
NET goes red the backend is down.

### Pointing at a different backend

```bash
VITE_BACKEND_BASE=https://my-backend.example.com npm run dev
```

The backend reads `ALLOWED_ORIGINS` (comma-separated) for CORS in production;
locally it permits the two Vite ports.

## Wire format

The client POSTs `ChatRequest` JSON to `/v1/chat` and parses the SSE
event stream by hand (browsers' `EventSource` is GET-only). Each frame is:

```
event: <name>
data: <json>
data: <json>            # optional, joined with \n
                        # blank line = end of frame
```

Recognised event names from `backend/icetea/api/sse.py`:

- `token`      `{ "delta": "..." }`        appended to the assistant bubble
- `meta`       `{ "stage": "...", ... }`   pushed into the trace pane
- `structured` `{ "agent": "...", ... }`   attached to the bubble + togglable
- `error`      `{ "code", "message" }`     renders the bubble red
- `done`       `{ ... }`                   final timestamp/latency

## Layout decisions worth knowing

- Browsers ship `EventSource` for GET-only SSE. Our backend takes POST,
  so the client uses `fetch` + `ReadableStream` and a tiny hand-rolled SSE
  frame parser. See `src/sseClient.ts`.
- No router, no state library, no Tailwind. The whole frontend is ~700
  LoC of TS + ~450 LoC of CSS, on purpose. The Bloomberg aesthetic
  doesn't want spinners or modal stacks.
- The trace pane caps at 400 entries (FIFO) so a long demo run doesn't
  push DOM nodes into the thousands.
- Switching profile resets the session id — otherwise the backend session
  store would hydrate the wrong user_context on the next turn.
