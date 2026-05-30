"""MCP-style risk / tax math server — 5 endpoints (toolkits + light stubs)."""
from __future__ import annotations

from typing import Any

from ..orchestration.toolkits import finance_math as fin_math
from ..orchestration.toolkits import overlap_tools as ov_tools
from ..orchestration.toolkits import portfolio_tools as port

SERVER_ID = "mcp_risk_tax"
SERVER_TITLE = "Risk, overlap & tax stubs (MCP shim)"


def endpoints() -> list[dict[str, Any]]:
    return [
        {"id": "tax_gain_bundle", "method": "POST", "path": "/v1/tax_gain", "summary": "Stub LTCG/STCG style gain bundle for one ticker."},
        {"id": "factor_overlap", "method": "POST", "path": "/v1/overlap", "summary": "Factor overlap stub across book."},
        {"id": "book_risk_flags", "method": "POST", "path": "/v1/book_risk", "summary": "Coarse book-level risk hints."},
        {"id": "liquidity_stub", "method": "POST", "path": "/v1/liquidity", "summary": "Liquidity / turnover stub (educational)."},
        {"id": "scenario_note", "method": "POST", "path": "/v1/scenario", "summary": "Single-name stress caption (not a sim engine)."},
    ]


def invoke(endpoint_id: str, *, user_context: dict[str, Any], query: str, ticker: str = "") -> dict[str, Any]:
    positions = port.list_positions(user_context)
    t = (ticker or "").strip().upper()
    if not t and positions:
        t = str(positions[0].get("ticker") or "").strip().upper()

    if endpoint_id == "tax_gain_bundle":
        return {"ok": True, "data": fin_math.toolkit_tax_gain_bundle(user_context, ticker=t or "UNKNOWN")}
    if endpoint_id == "factor_overlap":
        return {"ok": True, "data": ov_tools.toolkit_factor_overlap_stub(user_context)}
    if endpoint_id == "book_risk_flags":
        conc = port.flag_concentration(user_context)
        rp = port.snapshot_risk_profile(user_context)
        top_pct = conc.get("top_share_pct")
        top2_pct = conc.get("top2_share_pct")
        # Deterministic stress math using share-count proxy:
        # impact ≈ weight * shock (ignores correlations, hedges, and $ weights).
        stresses = []
        try:
            w = float(top_pct or 0.0) / 100.0
        except (TypeError, ValueError):
            w = 0.0
        for shock in (-10, -20, -35, -50):
            stresses.append(
                {
                    "shock_pct": shock,
                    "implied_portfolio_hit_pct": round(abs(w * float(shock)), 1),
                    "note": "share-count proxy; ignores correlations and $ weights",
                }
            )
        return {
            "ok": True,
            "data": {
                "concentration": conc,
                "risk_profile": rp,
                "stress_top_holding": {
                    "top_holding": conc.get("top_holding"),
                    "top_share_pct": top_pct,
                    "top2_share_pct": top2_pct,
                    "stress_cases": stresses,
                },
            },
        }
    if endpoint_id == "liquidity_stub":
        n = len(positions)
        return {
            "ok": True,
            "data": {
                "lines_on_file": n,
                "note": "Liquidity is inferred from line count only — no order-book or spread model ran.",
            },
        }
    if endpoint_id == "scenario_note":
        sym = t or "BOOK"
        return {
            "ok": True,
            "data": {
                "symbol": sym,
                "caption": f"Educational stress caption only — no path simulation ran for {sym}.",
            },
        }
    return {"ok": False, "error": "unknown_endpoint", "endpoint_id": endpoint_id}
