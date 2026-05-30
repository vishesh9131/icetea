"""MCP-style portfolio book server — 5 endpoints backed by ``portfolio_tools``."""
from __future__ import annotations

from typing import Any

from ..orchestration.toolkits import portfolio_tools as port

SERVER_ID = "mcp_portfolio_core"
SERVER_TITLE = "Portfolio book & profile (MCP shim)"


def endpoints() -> list[dict[str, Any]]:
    return [
        {"id": "positions", "method": "POST", "path": "/v1/positions", "summary": "List user positions snapshot."},
        {"id": "allocation", "method": "POST", "path": "/v1/allocation", "summary": "High-level sleeve / weight summary."},
        {"id": "concentration", "method": "POST", "path": "/v1/concentration", "summary": "Concentration flags vs coarse thresholds."},
        {"id": "risk_profile", "method": "POST", "path": "/v1/risk_profile", "summary": "Stated risk posture snapshot."},
        {"id": "match_tickers", "method": "POST", "path": "/v1/match_tickers", "summary": "Map query tickers to book lines."},
    ]


def invoke(endpoint_id: str, *, user_context: dict[str, Any], query: str, tickers: list[str] | None = None) -> dict[str, Any]:
    tks = tickers if tickers is not None else []
    if endpoint_id == "positions":
        return {"ok": True, "data": port.list_positions(user_context)}
    if endpoint_id == "allocation":
        return {"ok": True, "data": port.summarize_allocation(user_context)}
    if endpoint_id == "concentration":
        return {"ok": True, "data": port.flag_concentration(user_context)}
    if endpoint_id == "risk_profile":
        return {"ok": True, "data": port.snapshot_risk_profile(user_context)}
    if endpoint_id == "match_tickers":
        return {"ok": True, "data": port.match_tickers_to_positions(user_context, [str(x).upper() for x in tks][:12])}
    return {"ok": False, "error": "unknown_endpoint", "endpoint_id": endpoint_id}
