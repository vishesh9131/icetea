"""Inject MCP server catalog into ``user_context`` so every agent sees the same tool surface."""
from __future__ import annotations

from typing import Any

from .mcp_servers.registry import build_agent_visible_catalog


def attach_mcp_servers_to_context(user_context: dict[str, Any]) -> None:
    """Mutates ``user_context`` in place — idempotent per request."""
    if user_context.get("_mcp_servers_attached"):
        return
    user_context["mcp_servers"] = build_agent_visible_catalog()
    user_context["_mcp_servers_attached"] = True
