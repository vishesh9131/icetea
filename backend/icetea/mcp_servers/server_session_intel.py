"""MCP-style session / thread intel server — 5 endpoints backed by ``conversation_tools``."""
from __future__ import annotations

from typing import Any

from ..orchestration.toolkits import conversation_tools as conv

SERVER_ID = "mcp_session_intel"
SERVER_TITLE = "Session & thread helpers (MCP shim)"


def endpoints() -> list[dict[str, Any]]:
    return [
        {"id": "prior_user_turns", "method": "POST", "path": "/v1/priors", "summary": "Recent user lines from thread."},
        {"id": "thread_summary", "method": "POST", "path": "/v1/thread_stub", "summary": "Short deterministic thread recap stub."},
        {"id": "disclaimer", "method": "POST", "path": "/v1/disclaimer", "summary": "Standard toolkit disclaimer block."},
        {"id": "handoff_hint", "method": "POST", "path": "/v1/handoff", "summary": "Suggest downstream intent label."},
        {"id": "numbered_list", "method": "POST", "path": "/v1/format_list", "summary": "Format prior lines as numbered list."},
    ]


def invoke(
    endpoint_id: str,
    *,
    user_context: dict[str, Any],
    query: str,
    history: list[dict[str, str]] | None = None,
    last_intent: str | None = None,
) -> dict[str, Any]:
    hist = list(history or [])
    if endpoint_id == "prior_user_turns":
        return {"ok": True, "data": conv.toolkit_prior_user_turns(hist)}
    if endpoint_id == "thread_summary":
        return {"ok": True, "data": conv.toolkit_thread_summary_stub(hist)}
    if endpoint_id == "disclaimer":
        return {"ok": True, "data": conv.toolkit_disclaimer_block()}
    if endpoint_id == "handoff_hint":
        return {"ok": True, "data": conv.toolkit_suggest_handoff_intent(query, last_intent)}
    if endpoint_id == "numbered_list":
        priors = conv.toolkit_prior_user_turns(hist)
        return {"ok": True, "data": conv.toolkit_format_numbered_list(priors[-5:])}
    return {"ok": False, "error": "unknown_endpoint", "endpoint_id": endpoint_id}
