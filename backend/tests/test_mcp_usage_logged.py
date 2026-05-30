from __future__ import annotations


def test_supervisor_logs_mcp_calls_in_tool_results():
    from icetea.orchestration.supervisor import _portfolio_round, _market_round

    uc = {
        "user_id": "u1",
        "risk_profile": "moderate",
        "positions": [{"ticker": "NVDA", "quantity": 10}, {"ticker": "QQQ", "quantity": 5}],
    }
    p = _portfolio_round(uc)
    assert "_mcp_calls" in (p.get("tool_results") or {})
    assert (p["tool_results"]["_mcp_calls"] or [])[0]["server_id"].startswith("mcp_")

    m = _market_round(uc, "recession risk", p, round_no=2)
    assert "_mcp_calls" in (m.get("tool_results") or {})
    assert any(c["endpoint_id"] == "quote" for c in m["tool_results"]["_mcp_calls"])

