"""HTTP routes."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..agents import custom as custom_agents
from ..agents.registry import _KNOWN_NAMES, _REAL as REAL_AGENTS
from ..config import get_settings
from ..llm import LLMError, get_llm_client
from ..mcp_servers.registry import build_agent_visible_catalog
from ..pipeline import process_query
from .market_tape import get_tape
from .news_feed import get_market_news, get_portfolio_news
from .reader import fetch_article
from .schemas import ChatRequest
from .sse import stream_events


logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/healthz")
async def healthz() -> JSONResponse:
    s = get_settings()
    return JSONResponse(
        {
            "status": "ok",
            "llm_provider": s.llm_provider,
            "model": s.active_model,
            "app_env": s.app_env,
        }
    )


@router.get("/v1/meta")
async def meta() -> JSONResponse:
    """Static-ish service metadata for the UI header strip.

    Same shape as /healthz plus a service name + version. Frontend hits this
    on mount instead of guessing model / provider strings.
    """
    s = get_settings()
    return JSONResponse(
        {
            "service": "icetea",
            "version": "0.1.0",
            "app_env": s.app_env,
            "llm_provider": s.llm_provider,
            "model": s.active_model,
            "request_timeout_s": s.request_timeout_s,
            "multiagent_rounds": s.multiagent_rounds,
        }
    )


@router.get("/v1/market/tape")
async def market_tape() -> JSONResponse:
    """Live market ticker tape for the header ribbon.

    Cached for 45s; returns stale items immediately while a background
    refresh is in flight, so the UI never blocks on yfinance.
    """
    data = await get_tape()
    return JSONResponse(data)


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------

@router.get("/v1/news/market")
async def news_market() -> JSONResponse:
    """Latest news for the general market basket. Cached 5 min per ticker."""
    data = await get_market_news()
    return JSONResponse(data)


@router.get("/v1/news/portfolio")
async def news_portfolio(tickers: str = Query("", description="Comma-separated tickers")) -> JSONResponse:
    """Latest news for a specific portfolio. ``tickers`` is comma-separated."""
    tlist = [t.strip() for t in tickers.split(",") if t.strip()]
    data = await get_portfolio_news(tlist)
    return JSONResponse(data)


@router.get("/v1/reader/article")
async def reader_article(url: str = Query(..., description="https URL of the article to read")) -> JSONResponse:
    """Fetch + extract an article body for the in-app READER dock tile.

    Proxies through the SSRF-filtered web toolkit so the frontend never
    opens an external tab. The body is plain text (HTML stripped, ~12k
    char cap) and is cached for 15 minutes per URL.
    """
    data = await fetch_article(url)
    return JSONResponse(data)


# ---------------------------------------------------------------------------
# MCP catalog (for the agent builder UI)
# ---------------------------------------------------------------------------

@router.get("/v1/mcp/servers")
async def mcp_servers() -> JSONResponse:
    """Enumerate every MCP shim server + endpoint a custom agent can call."""
    return JSONResponse(build_agent_visible_catalog())


@router.get("/v1/tools/catalog")
async def tools_catalog() -> JSONResponse:
    """Flat tool catalog for the agent builder: web tools + MCP shim endpoints."""
    return JSONResponse({"tools": custom_agents.tool_catalog()})


# ---------------------------------------------------------------------------
# Agents (custom + built-in) CRUD
# ---------------------------------------------------------------------------

def _builtin_agents_meta() -> list[dict]:
    """Surface read-only metadata for the built-in agents that ship with Icetea.

    The UI shows these as "system" agents (non-editable) alongside any custom
    ones the operator has saved.
    """
    out = []
    for name in _KNOWN_NAMES:
        out.append({
            "id": name,
            "label": name.replace("_", " ").title(),
            "kind": "builtin",
            "implemented": name in REAL_AGENTS,
        })
    return out


@router.get("/v1/agents")
async def list_agents() -> JSONResponse:
    """Return every agent the pipeline can dispatch to.

    Shape: { builtin: [...], custom: [...] } where the custom list mirrors
    what is persisted in custom_agents.json.
    """
    custom = [c.__dict__ for c in custom_agents.load_all()]
    return JSONResponse({
        "builtin": _builtin_agents_meta(),
        "custom": custom,
    })


@router.post("/v1/agents")
async def upsert_agent(payload: dict) -> JSONResponse:
    """Create or overwrite a single custom agent definition (by id)."""
    try:
        d = custom_agents.CustomAgentDef.from_dict(payload or {})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"bad payload: {exc}")
    err = d.validate()
    if err:
        raise HTTPException(status_code=400, detail=err)
    # collision with a builtin id is rejected - we don't want to mask a real agent
    if d.id in _KNOWN_NAMES:
        raise HTTPException(status_code=409, detail=f"id '{d.id}' is reserved by a builtin agent")
    existing = custom_agents.load_all()
    by_id = {x.id: x for x in existing}
    by_id[d.id] = d
    custom_agents.save_all(list(by_id.values()))
    custom_agents.install_definition(d)
    return JSONResponse({"ok": True, "agent": d.__dict__})


@router.delete("/v1/agents/{agent_id}")
async def delete_agent(agent_id: str) -> JSONResponse:
    existing = custom_agents.load_all()
    keep = [x for x in existing if x.id != agent_id]
    if len(keep) == len(existing):
        raise HTTPException(status_code=404, detail=f"agent '{agent_id}' not found")
    custom_agents.save_all(keep)
    custom_agents.uninstall_definition(agent_id)
    return JSONResponse({"ok": True, "deleted": agent_id})


@router.post("/v1/chat")
async def chat(req: ChatRequest, request: Request) -> StreamingResponse:
    """SSE stream of pipeline events.

    SSE is the only response mode. There is no JSON fallback because the
    assignment forbids one and because mixing two response shapes leads
    to clients that quietly skip streaming.
    """
    user_context = req.user_context.model_dump() if req.user_context else {}
    try:
        llm = get_llm_client()
    except LLMError:
        llm = None
    events = process_query(
        query=req.query,
        session_id=req.session_id,
        user_context=user_context,
        collaborative=req.collaborative,
        llm=llm,
        agent_override=req.agent_override,
    )
    return StreamingResponse(
        stream_events(events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx hint, harmless elsewhere
        },
    )
