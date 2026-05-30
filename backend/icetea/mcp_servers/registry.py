"""Aggregate four MCP-style servers (5 endpoints each) + invoke router."""
from __future__ import annotations

from typing import Any

from . import server_market_tape as mod_market
from . import server_portfolio_core as mod_portfolio
from . import server_risk_tax as mod_risk
from . import server_session_intel as mod_session

_MODULES = (mod_market, mod_portfolio, mod_risk, mod_session)

_BY_ID: dict[str, Any] = {m.SERVER_ID: m for m in _MODULES}


def _assert_shape() -> None:
    for m in _MODULES:
        eps = m.endpoints()
        if len(eps) != 5:
            raise RuntimeError(f"MCP server {m.SERVER_ID} must expose exactly 5 endpoints, got {len(eps)}")


_assert_shape()


def build_agent_visible_catalog() -> dict[str, Any]:
    """Serializable catalog for LLM prompts — every agent gets this via ``user_context``."""
    servers: list[dict[str, Any]] = []
    total_eps = 0
    for m in _MODULES:
        eps = m.endpoints()
        total_eps += len(eps)
        servers.append(
            {
                "server_id": m.SERVER_ID,
                "title": getattr(m, "SERVER_TITLE", m.SERVER_ID),
                "endpoint_count": len(eps),
                "endpoints": eps,
            }
        )
    return {
        "mcp_layer": "icetea_shim_v1",
        "server_count": len(servers),
        "endpoint_total": total_eps,
        "servers": servers,
        "usage_note": (
            "Each endpoint is callable through the in-process MCP shim (same Python process as the agent). "
            "Use names only — do not invent extra tools. Results are educational stubs unless noted."
        ),
    }


def invoke_mcp(
    server_id: str,
    endpoint_id: str,
    *,
    user_context: dict[str, Any],
    query: str = "",
    history: list[dict[str, str]] | None = None,
    last_intent: str | None = None,
    ticker: str = "",
    tickers: list[str] | None = None,
) -> dict[str, Any]:
    mod = _BY_ID.get(server_id)
    if mod is None:
        return {"ok": False, "error": "unknown_server", "server_id": server_id}
    if mod is mod_session:
        return mod.invoke(endpoint_id, user_context=user_context, query=query, history=history, last_intent=last_intent)
    if mod is mod_market:
        return mod.invoke(endpoint_id, user_context=user_context, query=query, ticker=ticker)
    if mod is mod_portfolio:
        return mod.invoke(endpoint_id, user_context=user_context, query=query, tickers=tickers)
    return mod.invoke(endpoint_id, user_context=user_context, query=query, ticker=ticker)
