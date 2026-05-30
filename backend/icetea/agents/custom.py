"""Generic, user-configurable agent runtime.

The agent builder UI persists definitions to ``backend/Logs/custom_agents.json``
and registers them with the existing AGENT_REGISTRY at import / hot-reload
time. Each definition is a thin record:

    {
      "id": "web_research",
      "label": "Web Research",
      "description": "search the web and summarise findings",
      "system_prompt": "you are a research assistant...",
      "tools": ["web_search", "fetch_url"],
      "temperature": 0.4,
      "max_tokens": 700
    }

At request time we instantiate one ``GenericCustomAgent`` per definition,
call the requested tools, attach their results into the LLM prompt, then
stream the narrative back through the same async-iterator protocol every
real agent uses (data + structured events). MCP shim endpoints + the web
toolkit are exposed as the available tool catalog.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, AsyncIterator

from ..config import get_settings
from ..llm import LLMError, assemble_messages
from ._streaming import stream_pieces

# NB: imports for mcp_servers.registry / orchestration.toolkits.web_tools are
# deferred inside the helpers below. Pulling them at module load triggers a
# circular import (orchestration/__init__.py imports the supervisor, which
# imports mcp_servers.registry, which imports us via the agent registry).

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool catalog - everything a custom agent can call.
# Each entry has a stable "tool_id" the UI can show + a runner.
# ---------------------------------------------------------------------------


@dataclass
class ToolSpec:
    tool_id: str
    label: str
    description: str
    inputs: list[str] = field(default_factory=list)
    group: str = "general"


def _mcp_shim_tools() -> list[ToolSpec]:
    """Wrap the in-process MCP shim endpoints as flat tool descriptors."""
    from ..mcp_servers.registry import build_agent_visible_catalog  # deferred
    cat = build_agent_visible_catalog()
    out: list[ToolSpec] = []
    for srv in cat.get("servers", []):
        sid = srv["server_id"]
        for ep in srv.get("endpoints", []):
            ep_id = ep.get("id") or ep.get("name") or ""
            if not ep_id:
                continue
            out.append(
                ToolSpec(
                    tool_id=f"mcp::{sid}::{ep_id}",
                    label=f"{sid.replace('mcp_', '').replace('_', ' ').upper()} · {ep_id}",
                    description=str(ep.get("description") or ep.get("summary") or "")[:160],
                    inputs=list(ep.get("required_inputs") or []),
                    group=sid,
                )
            )
    return out


_WEB_TOOLS: list[ToolSpec] = [
    ToolSpec(
        tool_id="web_search",
        label="WEB · search (DuckDuckGo)",
        description="Search the open web. Returns up to 5 {title, url, snippet} hits.",
        inputs=["query"],
        group="web",
    ),
    ToolSpec(
        tool_id="fetch_url",
        label="WEB · fetch URL",
        description="HTTPS GET an article and return a plain-text excerpt (SSRF-filtered, ~12k chars).",
        inputs=["url"],
        group="web",
    ),
]


def tool_catalog() -> list[dict[str, Any]]:
    """Flat list of every callable tool a custom agent can opt into."""
    return [asdict(t) for t in (_WEB_TOOLS + _mcp_shim_tools())]


def _exec_tool(
    tool_id: str,
    *,
    query: str,
    user_context: dict[str, Any],
) -> dict[str, Any]:
    """Run a single tool. Returns {ok, tool, output, error?}.

    The output shape is whatever the underlying toolkit returns - the LLM
    sees the raw JSON, so consistency matters less than capturing every
    relevant field.
    """
    # deferred imports: see top-of-file comment about circular import
    try:
        if tool_id == "web_search":
            from ..orchestration.toolkits import web_tools as wt
            res = wt.toolkit_web_search(query)
            return {"ok": True, "tool": tool_id, "output": res}
        if tool_id == "fetch_url":
            from ..orchestration.toolkits import web_tools as wt
            url = query.strip()
            if not url.lower().startswith(("http://", "https://")):
                return {"ok": False, "tool": tool_id, "error": "fetch_url needs a URL in the query"}
            res = wt.toolkit_fetch_url(url)
            return {"ok": True, "tool": tool_id, "output": res}
        if tool_id.startswith("mcp::"):
            from ..mcp_servers.registry import invoke_mcp
            _, server_id, endpoint_id = tool_id.split("::", 2)
            res = invoke_mcp(server_id, endpoint_id, user_context=user_context, query=query)
            return {"ok": True, "tool": tool_id, "output": res}
    except Exception as exc:
        logger.warning("custom agent tool %s failed: %s", tool_id, exc)
        return {"ok": False, "tool": tool_id, "error": str(exc)}
    return {"ok": False, "tool": tool_id, "error": "unknown_tool"}


# ---------------------------------------------------------------------------
# Definition + JSON-file persistence
# ---------------------------------------------------------------------------

_VALID_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


@dataclass
class CustomAgentDef:
    id: str
    label: str
    description: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    temperature: float = 0.3
    max_tokens: int = 700

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "CustomAgentDef":
        return CustomAgentDef(
            id=str(d.get("id", "")).strip().lower(),
            label=str(d.get("label", "")).strip() or str(d.get("id", "")),
            description=str(d.get("description", "")).strip(),
            system_prompt=str(d.get("system_prompt", "")).strip(),
            tools=[str(t) for t in (d.get("tools") or [])],
            temperature=float(d.get("temperature", 0.3)),
            max_tokens=int(d.get("max_tokens", 700)),
        )

    def validate(self) -> str | None:
        if not _VALID_ID.match(self.id):
            return "id must be snake_case (letters/digits/underscore, 2-40 chars, starts with a letter)"
        if not self.system_prompt:
            return "system_prompt is required"
        if not self.label:
            return "label is required"
        if self.temperature < 0 or self.temperature > 2:
            return "temperature must be in [0, 2]"
        if self.max_tokens < 32 or self.max_tokens > 4000:
            return "max_tokens must be in [32, 4000]"
        valid_tools = {t["tool_id"] for t in tool_catalog()}
        for t in self.tools:
            if t not in valid_tools:
                return f"unknown tool: {t}"
        return None


def _store_path() -> Path:
    # Stored next to other on-disk artifacts; honour SESSION_MEMORY_DIR's parent
    # so test runs don't pollute the dev file.
    s = get_settings()
    if s.app_env == "test":
        return Path("Logs") / "custom_agents.test.json"
    return Path("Logs") / "custom_agents.json"


def load_all() -> list[CustomAgentDef]:
    p = _store_path()
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("custom_agents.json unreadable: %s", exc)
        return []
    if not isinstance(raw, list):
        return []
    out: list[CustomAgentDef] = []
    for entry in raw:
        try:
            d = CustomAgentDef.from_dict(entry)
            if d.validate() is None:
                out.append(d)
        except Exception:
            continue
    return out


def save_all(defs: list[CustomAgentDef]) -> None:
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps([asdict(d) for d in defs], indent=2), encoding="utf-8")
    os.replace(tmp, p)


# ---------------------------------------------------------------------------
# Runtime agent
# ---------------------------------------------------------------------------

class GenericCustomAgent:
    """Single class that runs any user-defined CustomAgentDef.

    Lifecycle per request:
      1. If the definition has tools, call each one with the user's query as
         the input. We do this synchronously (the tools are cheap and the
         pipeline already runs us inside an async iterator).
      2. Build messages = [system_prompt, history, user(query + tool results)].
      3. Stream the LLM response back as data events.
      4. Emit a structured event at the end with tool outputs + agent meta.
    """

    def __init__(self, definition: CustomAgentDef) -> None:
        self._def = definition
        self.name = definition.id

    async def run(
        self,
        *,
        query: str,
        user_context: dict[str, Any],
        classification: dict[str, Any],
        llm: Any | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        d = self._def
        tool_results: list[dict[str, Any]] = []
        for tool_id in d.tools:
            yield {"type": "meta", "stage": "tool_call", "tool": tool_id}
            # tool calls are sync - run them in a thread to keep the event loop free
            res = await asyncio.to_thread(_exec_tool, tool_id, query=query, user_context=user_context)
            tool_results.append(res)
            yield {"type": "meta", "stage": "tool_result", "tool": tool_id, "ok": res.get("ok", False)}

        tool_blob = json.dumps(tool_results, default=str, indent=2)[:6000] if tool_results else ""
        user_msg = query if not tool_blob else (
            f"{query}\n\n[TOOL_RESULTS]\n{tool_blob}\n\nUse the tool results above when relevant. "
            f"Cite URLs explicitly when you draw on web sources."
        )

        # Build messages. We drop the trailing user turn from history (the
        # pipeline persists it before invoking us) to avoid duplication.
        hist = list(conversation_history or [])
        if hist and hist[-1].get("role") == "user":
            hist = hist[:-1]
        messages = assemble_messages(system=d.system_prompt, history=hist, user=user_msg)

        narrative_chunks: list[str] = []
        client = llm if (llm is not None and hasattr(llm, "stream_text")) else None
        if client is None:
            fallback = (
                f"[{d.label} - offline] No LLM is configured. The tool calls "
                f"above ran but no narrative can be generated."
            )
            yield {"type": "data", "delta": fallback}
            narrative_chunks.append(fallback)
        else:
            had_content = False
            try:
                async for channel, piece in stream_pieces(
                    client,
                    messages,
                    temperature=d.temperature,
                    max_tokens=d.max_tokens,
                ):
                    if channel == "think":
                        yield {"type": "thinking", "delta": piece}
                        continue
                    had_content = True
                    narrative_chunks.append(piece)
                    yield {"type": "data", "delta": piece}
            except LLMError as exc:
                msg = f"\n\n[{d.label} - LLM error: {exc}]"
                narrative_chunks.append(msg)
                yield {"type": "data", "delta": msg}
                had_content = True
            if not had_content:
                # CoT consumed the budget on a thinking model; emit a
                # short note so the user is not stuck with a blank bubble
                msg = (
                    f"\n\n[{d.label} - model spent all tokens on chain-of-thought; "
                    "raise max_tokens in the agent definition to leave room "
                    "for the answer.]"
                )
                narrative_chunks.append(msg)
                yield {"type": "data", "delta": msg}

        yield {
            "type": "structured",
            "payload": {
                "agent": d.id,
                "agent_label": d.label,
                "custom": True,
                "tools_called": [t.get("tool") for t in tool_results],
                "tool_results": tool_results,
                "narrative_chars": sum(len(c) for c in narrative_chunks),
            },
        }


# ---------------------------------------------------------------------------
# Registry helpers - called by the API routes on CRUD + at startup.
# ---------------------------------------------------------------------------

# Track which ids we registered so we can unregister cleanly on update/delete.
_OWNED_IDS: set[str] = set()


def register_all_into_agent_registry() -> int:
    """Load definitions from disk and register each one with the global agent
    registry. Returns the number of agents registered. Idempotent."""
    from . import registry as agent_registry

    defs = load_all()
    count = 0
    for d in defs:
        agent_registry.register(d.id, GenericCustomAgent(d))
        _OWNED_IDS.add(d.id)
        count += 1
    return count


def install_definition(d: CustomAgentDef) -> None:
    """Register a single (possibly new) definition. Caller persists to disk."""
    from . import registry as agent_registry

    agent_registry.register(d.id, GenericCustomAgent(d))
    _OWNED_IDS.add(d.id)


def uninstall_definition(agent_id: str) -> None:
    """Drop a custom agent from the runtime registry. Caller persists to disk."""
    from . import registry as agent_registry

    # registry._REAL is a private detail - we mutate it carefully and only
    # for ids we ourselves registered.
    if agent_id in _OWNED_IDS:
        agent_registry._REAL.pop(agent_id, None)
        _OWNED_IDS.discard(agent_id)
