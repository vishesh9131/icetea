"""Four MCP-style servers (5 endpoints each) for agent-side tooling."""

from .registry import build_agent_visible_catalog, invoke_mcp

__all__ = ["build_agent_visible_catalog", "invoke_mcp"]
