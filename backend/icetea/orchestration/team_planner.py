"""Orchestrator-chosen discussion panel: registry agent order + voice labels.

Priority: (1) classifier ``task_decomposition.discussion_team`` when populated,
(2) dedicated LLM plan over the full allowlist, (3) role heuristics via
``team_router`` mapped to registry names.

Registry import stays lazy so we dont trip the product_recommendation ->
web_tools import cycle at module load.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from ..llm import LLMClient, LLMError, assemble_messages
from ..safety import MODEL_INJECTION_GUARD
from . import team_router

logger = logging.getLogger(__name__)

# legacy panel role -> registry id (same mapping intent_decompose uses)
_ROLE_TO_REGISTRY: dict[str, str] = {
    "portfolio": "portfolio_health",
    "market": "market_research",
    "tax_math": "investment_strategy",
    "risk": "risk_assessment",
    "momentum": "investment_strategy",
}

_TAXISH = re.compile(
    r"\b(tax|taxes|capital\s+gains?|ltcg|stcg|harvest|taxable|lot)\b",
    re.I,
)


@dataclass(frozen=True)
class PanelSlot:
    registry_agent: str
    voice: str


@dataclass(frozen=True)
class TeamPlan:
    slots: list[PanelSlot]
    source: str
    rationale: str | None = None


def _known_agent_names() -> tuple[str, ...]:
    from ..agents.registry import known_agent_names

    return known_agent_names()


def discussion_agent_ids_from_roles(
    query: str,
    classification_agent: str,
    entities: dict[str, Any],
    user_context: dict[str, Any],
) -> list[str]:
    """Map legacy role heuristics to registry ids (used when classifier omits ``discussion_team``)."""
    cls = {"agent": classification_agent, "entities": entities or {}}
    roles = team_router.select_specialist_roles(query, cls, user_context)
    return [_ROLE_TO_REGISTRY[r] for r in roles if r in _ROLE_TO_REGISTRY][:8]


def _slots_from_agent_names_with_voices(pairs: list[tuple[str, str]], *, source: str, rationale: str | None) -> TeamPlan | None:
    allow = set(_known_agent_names())
    slots: list[PanelSlot] = []
    for agent, voice in pairs:
        a = str(agent).strip()
        v = str(voice).strip() or a
        if a not in allow:
            continue
        slots.append(PanelSlot(registry_agent=a, voice=v))
    if len(slots) < 2:
        return None
    return TeamPlan(slots=slots[:8], source=source, rationale=rationale)


def slots_from_classifier_team(names: list[str], *, query: str = "") -> TeamPlan | None:
    """Build slots from classifier ``discussion_team`` (agent ids only)."""
    if not names:
        return None
    allow = set(_known_agent_names())
    cleaned = [str(x).strip() for x in names if str(x).strip() in allow]
    if len(cleaned) < 2:
        return None
    slots: list[PanelSlot] = []
    strat_n = 0
    for a in cleaned:
        if a == "investment_strategy":
            strat_n += 1
            if strat_n == 1:
                voice = "tax_math" if _TAXISH.search(query or "") else "momentum"
            else:
                voice = "momentum" if strat_n % 2 == 0 else "tax_math"
        elif a == "portfolio_health":
            voice = "portfolio"
        elif a == "market_research":
            voice = "market"
        elif a == "risk_assessment":
            voice = "risk"
        else:
            voice = a
        slots.append(PanelSlot(registry_agent=a, voice=voice))
    return TeamPlan(slots=slots[:8], source="classifier")


def heuristic_slots(query: str, classification: dict[str, Any], user_context: dict[str, Any]) -> TeamPlan:
    roles = team_router.select_specialist_roles(query, classification, user_context)
    pairs: list[tuple[str, str]] = []
    for r in roles:
        reg = _ROLE_TO_REGISTRY.get(r)
        if reg:
            pairs.append((reg, r))
    if len(pairs) < 2:
        # shouldnt happen — team_router always returns at least default size
        pairs = [
            ("portfolio_health", "portfolio"),
            ("market_research", "market"),
        ]
    return TeamPlan(slots=[PanelSlot(*p) for p in pairs[:8]], source="heuristic_roles")


_TEAM_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["team", "rationale"],
    "properties": {
        "team": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["agent", "voice"],
                "properties": {
                    "agent": {"type": "string"},
                    "voice": {"type": "string"},
                },
            },
            "minItems": 2,
            "maxItems": 8,
        },
        "rationale": {"type": "string"},
    },
}

_SYS_ORCH = """You orchestrate a multi-agent discussion for a novice-investor product.

Pick an ordered team of specialist agents. Order matters: index 0 speaks first in the thread.
Only use agent ids from allowed_agents (exact spelling). Pick 2–6 agents unless the question truly needs more (hard cap 8).
Match the user question — skip agents that have nothing to add. If the user has no portfolio data and asks purely about macro, you may omit portfolio_health.

Return JSON only (schema supplied). rationale: one short sentence why this lineup fits.

""" + "\n\n" + MODEL_INJECTION_GUARD


async def _llm_plan_slots(
    llm: LLMClient,
    *,
    query: str,
    classification: dict[str, Any],
    user_context: dict[str, Any],
) -> TeamPlan | None:
    allow = list(_known_agent_names())
    blob = {
        "user_question": query,
        "classification": {
            "agent": classification.get("agent"),
            "intent": classification.get("intent"),
            "entities": classification.get("entities") or {},
        },
        "allowed_agents": allow,
        "has_positions": bool((user_context.get("positions") or [])),
    }

    def _call() -> dict[str, Any]:
        messages = assemble_messages(
            system=_SYS_ORCH,
            user=json.dumps(blob, indent=2, default=str),
        )
        return llm.complete_json(
            messages,
            json_schema=_TEAM_PLAN_SCHEMA,
            temperature=0.25,
            max_tokens=500,
        )

    try:
        raw = await asyncio.to_thread(_call)
    except (LLMError, Exception) as exc:
        logger.warning("LLM team planner failed: %s", exc)
        return None

    if not isinstance(raw, dict):
        return None
    team = raw.get("team")
    rationale = str(raw.get("rationale") or "").strip() or None
    if not isinstance(team, list):
        return None
    pairs: list[tuple[str, str]] = []
    for row in team:
        if not isinstance(row, dict):
            continue
        a = str(row.get("agent") or "").strip()
        v = str(row.get("voice") or "").strip() or a
        pairs.append((a, v))
    plan = _slots_from_agent_names_with_voices(pairs, source="llm_orchestrator", rationale=rationale)
    return plan


def query_sounds_taxish(query: str) -> bool:
    return bool(_TAXISH.search(query or ""))


def collab_speaker_key(slot: PanelSlot, query: str) -> str:
    """Map a panel slot to collaborative_llm discussion role keys."""
    v = slot.voice
    if v in ("portfolio", "market", "tax_math", "risk", "momentum"):
        return v
    if slot.registry_agent == "portfolio_health":
        return "portfolio"
    if slot.registry_agent == "market_research":
        return "market"
    if slot.registry_agent == "investment_strategy":
        if query_sounds_taxish(query):
            return "tax_math"
        return "momentum"
    return "risk"


async def plan_discussion_team(
    *,
    query: str,
    classification: dict[str, Any],
    user_context: dict[str, Any],
    llm: Any,
) -> TeamPlan:
    td = classification.get("task_decomposition") or {}
    dt = td.get("discussion_team")
    if isinstance(dt, list) and len(dt) >= 2:
        from_cls = slots_from_classifier_team([str(x).strip() for x in dt if str(x).strip()], query=query)
        if from_cls is not None:
            return from_cls

    if llm is not None and isinstance(llm, LLMClient):
        planned = await _llm_plan_slots(llm, query=query, classification=classification, user_context=user_context)
        if planned is not None:
            return planned

    return heuristic_slots(query, classification, user_context)
