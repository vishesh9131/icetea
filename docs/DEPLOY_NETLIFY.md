# Netlify + Render deploy

Netlify hosts the **static UI** (landing + terminal). The **Python API cannot run on Netlify** (only JS/Go functions are supported). The API runs on **Render** (free tier); Netlify proxies `/healthz` and `/v1/*` to it so the browser still sees one origin.

## Architecture

```
Browser  →  icetea1.netlify.app/app/     (terminal UI)
         →  icetea1.netlify.app/v1/*    (Netlify JS proxy)
         →  icetea-api.onrender.com/v1/* (FastAPI)
```

## Step 1 — Deploy backend on Render

1. Push this repo to GitHub.
2. Go to [render.com](https://render.com) → **New** → **Blueprint** → connect repo.
3. Render reads `render.yaml` and creates **icetea-api**.
4. In Render, set env vars (same keys as your local `.env`):
   - `LLM_PROVIDER`, `OPENAI_API_KEY` and/or `VLLM_BASE_URL`, etc.
5. Wait for deploy; copy the service URL, e.g. `https://icetea-api.onrender.com`.

Test: `curl https://icetea-api.onrender.com/healthz` → `{"status":"ok",...}`

## Step 2 — Netlify env

In **icetea1** → Site configuration → Environment variables:

| Variable | Value |
|----------|--------|
| `BACKEND_URL` | `https://icetea-api.onrender.com` *(no trailing slash)* |
| `LLM_PROVIDER`, `OPENAI_API_KEY`, etc. | **Not needed on Netlify** — only on Render |

Remove empty vars you don't use (`DATABASE_URL`, `REDIS_URL`, `PGVECTOR_DATABASE_URL` — this app doesn't need them).

## Step 3 — Netlify build settings

| Setting | Value |
|---------|--------|
| Base directory | *(empty)* |
| Build command | `bash scripts/build-netlify-unified.sh` |
| Publish directory | `dist` |
| Functions directory | `netlify/functions` |

**Deploys → Trigger deploy → Clear cache and deploy site**

## Step 4 — Verify

| URL | Expected |
|-----|----------|
| `/healthz` | JSON `status: ok` (proxied from Render) |
| `/app/` | Terminal, **NET LIVE** |
| `/app/profiles.json` | JSON profiles file |
| Chat | Streams after Render cold start (~30s first hit on free tier) |

If `/healthz` returns `BACKEND_URL not configured`, you forgot Step 2.

## Local dev

```bash
make dev   # :8000 API + :5173 terminal — no proxy needed
```

## Free tier notes

- **Render free**: spins down after ~15 min idle; first request is slow.
- **Netlify proxy**: no 10s Python limit — SSE streams from Render through the JS proxy.
- **COLLAB / long runs**: work on Render; not limited by Netlify function timeout.

## Legacy split sites

Old `icetea-landing` + `icetea-terminal` Netlify projects can be retired once icetea1 works.
