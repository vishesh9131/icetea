# Netlify — one site (landing + terminal + serverless API)

Everything ships as a **single** Netlify project: marketing pages at `/`, the Bloomberg terminal at `/app`, and the FastAPI backend as a **serverless function** (no separate Render/Railway host).

## Live URLs (after deploy)

| What | Path |
|------|------|
| Landing | `https://YOUR-SITE.netlify.app/` |
| Terminal | `https://YOUR-SITE.netlify.app/app/` |
| API | same origin — `/healthz`, `/v1/*` |

Older split deploys (`icetea-landing` + `icetea-terminal`) still work; this layout replaces them when you want one free site.

## Deploy

```bash
# from repo root
bash scripts/build-netlify-unified.sh   # optional local check
netlify link                            # once, pick or create a site
netlify deploy --prod
```

Or connect GitHub: **Base directory** = repo root, **Build command** = `bash scripts/build-netlify-unified.sh`, **Publish** = `dist`.

## Required environment variables (Netlify UI)

Set under **Site configuration → Environment variables** (production scope).

| Variable | Required | Notes |
|----------|----------|--------|
| `OPENAI_API_KEY` | one of | When `LLM_PROVIDER=openai` |
| `ANTHROPIC_API_KEY` | one of | When `LLM_PROVIDER=claude` |
| `LLM_PROVIDER` | no | `openai` (default), `claude`, or `vllm` |
| `VLLM_BASE_URL` / `VLLM_MODEL` | if vllm | Self-hosted OpenAI-compatible endpoint |
| `MULTIAGENT_ENABLED` | no | `true` to allow COLLAB without toggling each request |

`SESSION_MEMORY_DIR` and `VITE_TERMINAL_URL` are set in root `netlify.toml` for the unified build.

## Local dev (unchanged)

```bash
make dev   # uvicorn :8000 + vite :5173
```

Unified paths are production-only. Locally the terminal still uses `http://127.0.0.1:8000` unless you set `VITE_BACKEND_BASE`.

## Free tier limits (important)

Netlify **serverless functions** on the free plan have a **~10 second** execution cap per invocation. That affects:

- Long **COLLAB** / multi-agent turns (can run 30–90s on a VPS)
- **SSE chat** that stays open for the whole model run

Short queries, news, tape, and quick agent replies usually fit. For heavy COLLAB on production, either:

- Keep `MULTIAGENT_ENABLED=false` on Netlify, or  
- Host the API on a long-running service (Render/Railway) and set `VITE_BACKEND_BASE` when building the terminal.

Streaming tokens work when the function stays under the time limit; there is no always-on Python process on Netlify.

## How the backend is wired

- `netlify/functions/server/server.py` — Mangum wraps `icetea.api.app:app`
- `netlify.toml` redirects `/healthz` and `/v1/*` to `/.netlify/functions/server` with `force = true`
- `included_files` bundles `backend/icetea/**` and fixtures

## Redeploy

```bash
netlify deploy --prod
```

## Split sites (legacy)

If you still use two Netlify projects, keep `Landing-site/netlify.toml` and `frontend/netlify.toml`. Set `VITE_TERMINAL_URL` on the landing site and `VITE_BACKEND_BASE` on the terminal to your external API URL.
