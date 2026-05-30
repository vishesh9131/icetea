"""MCP-style market tape server — 5 endpoints backed by ``market_tools``."""
from __future__ import annotations

from typing import Any

from ..orchestration.toolkits import market_tools as mkt

SERVER_ID = "mcp_market_tape"
SERVER_TITLE = "Market tape & listings (MCP shim)"


def endpoints() -> list[dict[str, Any]]:
    return [
        {"id": "quote", "method": "POST", "path": "/v1/quote", "summary": "Last price + sector for one symbol."},
        {"id": "returns_window", "method": "POST", "path": "/v1/returns", "summary": "Trailing return stats over N days."},
        {"id": "sector_benchmark", "method": "POST", "path": "/v1/sector_benchmark", "summary": "Sector benchmark stub vs symbol."},
        {"id": "resolve_symbol", "method": "POST", "path": "/v1/resolve", "summary": "Symbol normalization / alias hints."},
        {"id": "market_hours", "method": "POST", "path": "/v1/hours", "summary": "Session hours stub for a venue."},
    ]


def invoke(endpoint_id: str, *, user_context: dict[str, Any], query: str, ticker: str = "") -> dict[str, Any]:
    positions = user_context.get("positions") or []
    sym = (ticker or "").strip().upper()
    if not sym and isinstance(positions, list) and positions:
        sym = str(positions[0].get("ticker") or "SPY").strip().upper() or "SPY"
    if not sym:
        sym = "SPY"

    if endpoint_id == "quote":
        return {"ok": True, "data": mkt.toolkit_get_quote(sym)}
    if endpoint_id == "returns_window":
        return {"ok": True, "data": mkt.toolkit_get_recent_returns(sym, days=21)}
    if endpoint_id == "sector_benchmark":
        qinfo = mkt.toolkit_get_quote(sym)
        sector = qinfo.get("sector") if isinstance(qinfo, dict) else None
        return {"ok": True, "data": mkt.toolkit_sector_benchmark_stub(sector)}
    if endpoint_id == "resolve_symbol":
        return {"ok": True, "data": mkt.toolkit_symbol_resolve(sym)}
    if endpoint_id == "market_hours":
        return {"ok": True, "data": mkt.toolkit_market_hours_stub("US")}
    return {"ok": False, "error": "unknown_endpoint", "endpoint_id": endpoint_id}
