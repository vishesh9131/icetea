"""MCP shim layer: four logical servers, five endpoints each on every agent path."""
from __future__ import annotations

from icetea.mcp_servers.registry import build_agent_visible_catalog, invoke_mcp


def test_catalog_four_servers_twenty_endpoints():
    cat = build_agent_visible_catalog()
    assert cat.get("server_count") == 4
    assert cat.get("endpoint_total") == 20
    for s in cat["servers"]:
        assert len(s["endpoints"]) == 5


def test_invoke_routes_session_intel():
    out = invoke_mcp(
        "mcp_session_intel",
        "disclaimer",
        user_context={},
        query="hi",
        history=[{"role": "user", "content": "hello"}],
    )
    assert out.get("ok") is True
    assert "Educational" in str(out.get("data") or "")
