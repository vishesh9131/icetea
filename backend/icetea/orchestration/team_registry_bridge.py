"""Run ``icetea.agents`` registry agents inside a multi-agent panel turn.

Lazy registry import — product_recommendation agent drags web_tools which
would otherwise circle back into orchestration at import time.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegistryTurnOutcome:
    text: str
    registry_agent: str


async def collect_registry_panel_turn(
    *,
    registry_agent: str,
    voice: str,
    query: str,
    transcript: list[dict[str, Any]],
    shared_facts: dict[str, Any],
    extra_context: dict[str, Any],
    user_context: dict[str, Any],
    classification: dict[str, Any],
    conversation_history: list[dict[str, str]],
    llm: Any,
) -> RegistryTurnOutcome | None:
    from ..agents.registry import get_agent, known_agent_names

    if registry_agent not in known_agent_names():
        return None

    panel_blob = {
        "panel_instruction": (
            f"You are registry agent `{registry_agent}` speaking with voice `{voice}` "
            "in a live multi-agent thread. Other agents already spoke — engage with substance, "
            "use numeric_facts when it helps, stay educational. One focused reply."
        ),
        "original_user_question": query,
        "thread_so_far": transcript,
        "numeric_facts": shared_facts,
        "extra_context": extra_context,
        "mcp_servers": user_context.get("mcp_servers"),
    }
    wrapped = (
        "[MULTI_AGENT_PANEL]\n"
        + json.dumps(panel_blob, indent=2, default=str)
        + "\n\nSpeak to the investor in plain prose (not JSON)."
    )

    cls = dict(classification)
    cls["agent"] = registry_agent
    td = dict(cls.get("task_decomposition") or {}) if isinstance(cls.get("task_decomposition"), dict) else {}
    td["panel_speaker_role"] = voice
    td["agent_team_discussion"] = True
    cls["task_decomposition"] = td

    agent = get_agent(registry_agent)
    parts: list[str] = []
    try:
        async for ev in agent.run(
            query=wrapped,
            user_context=user_context,
            classification=cls,
            llm=llm,
            conversation_history=conversation_history,
        ):
            if ev.get("type") == "data":
                parts.append(str(ev.get("delta") or ""))
    except Exception as exc:
        logger.warning("Registry agent %s (voice=%s) failed: %s", registry_agent, voice, exc)
        return None

    text = "".join(parts).strip()
    if not text:
        return None
    return RegistryTurnOutcome(text=text, registry_agent=registry_agent)
