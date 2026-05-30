"""Heuristic multi-domain flags when the router forgets to spell things out."""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from .classifier import Classification
from .orchestration.toolkits import portfolio_tools as port_tools

_TAXISH = re.compile(
    r"\b(tax|taxes|taxable|capital\s+gains?|ltcg|stcg|short[- ]term|long[- ]term|harvest)\b",
    re.I,
)
_TEAM_PHRASE = re.compile(
    r"\b(debate|roundtable|multiple\s+perspectives|work\s+as\s+a\s+team|panel\s+of\s+agents|agents?\s+discuss|"
    r"hear\s+from\s+each\s+analyst|team\s+discussion|discuss\s+together)\b",
    re.I,
)
_RETIREMENT_PHRASE = re.compile(
    r"\b(retire(?:ment)?|fire\b|early\s+retire|passive\s+income|monthly\s+income|nest\s*egg|"
    r"safe\s+withdrawal|withdrawal\s+rate|long[- ]term\s+plan|roadmap|corpus|"
    r"buy\s+(?:a\s+)?(?:house|home)|house\s+in\s+\d|saving\s+for\s+(?:a\s+)?(?:house|home)|"
    r"down\s*payment|first[- ]time\s+home|mortgage)\b",
    re.I,
)
_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")
_BOGUS = frozenset(
    {
        "I",
        "A",
        "AN",
        "AS",
        "AT",
        "BE",
        "BY",
        "DO",
        "GO",
        "IF",
        "IN",
        "IS",
        "IT",
        "ME",
        "MY",
        "NO",
        "OF",
        "ON",
        "OR",
        "SO",
        "TO",
        "UP",
        "WE",
        "OK",
    }
)


def _tickers_from_query(query: str, positions: list[dict[str, Any]]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for p in positions:
        t = str(p.get("ticker") or "").strip().upper()
        if t and t not in seen:
            seen.add(t)
            ordered.append(t)
    for raw in _TICKER_RE.findall(query or ""):
        t = raw.upper()
        if len(t) < 2 or t in _BOGUS:
            continue
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    return ordered[:8]


def merge_task_decomposition(
    classification: Classification,
    query: str,
    user_context: dict[str, Any],
) -> Classification:
    td = dict(classification.task_decomposition or {})
    td.setdefault("primary_theme", None)
    td.setdefault("sub_tasks", list(td.get("sub_tasks") or []))
    td.setdefault("domains", [str(d).lower() for d in (td.get("domains") or [])])
    td.setdefault("requires_multi_agent", bool(td.get("requires_multi_agent")))

    if classification.agent == "investment_debate":
        td["primary_theme"] = td.get("primary_theme") or "investment_debate"
        td["requires_multi_agent"] = True
        subs = list(td["sub_tasks"])
        for label in ("bull_case_generation", "bear_case_generation", "long_horizon_analysis"):
            if label not in subs:
                subs.append(label)
        td["sub_tasks"] = subs
        doms = set(td["domains"])
        doms.update({"strategy", "fundamentals", "risk"})
        td["domains"] = sorted(doms)

    q = (query or "").strip()
    ql = q.lower()
    ents = classification.entities or {}
    has_tax = bool(_TAXISH.search(q))
    has_sell = ents.get("action") == "sell" or bool(re.search(r"\b(sell|selling)\b", ql))

    positions = port_tools.list_positions(user_context)
    tickers = [str(t).strip().upper() for t in (ents.get("tickers") or []) if str(t).strip()]
    if not tickers:
        tickers = _tickers_from_query(q, positions)

    # nvda / timing / capital gains style mashups
    if has_tax and has_sell and tickers:
        td["requires_multi_agent"] = True
        doms = set(td["domains"])
        doms.update({"tax", "market", "strategy"})
        td["domains"] = sorted(doms)
        if not td.get("primary_theme"):
            td["primary_theme"] = "tax_timing_tradeoff"
        subs = list(td["sub_tasks"])
        for label in ("capital_gains_context", "market_timing", "strategy_tradeoffs"):
            if label not in subs:
                subs.append(label)
        td["sub_tasks"] = subs
    elif td.get("requires_multi_agent"):
        doms = set(td["domains"])
        if "tax" in doms and "market" not in doms:
            doms.add("market")
        td["domains"] = sorted(doms)

    # free-form multi-agent thread (orchestrator picks specialists; they debate then synthesis)
    if classification.agent == "investment_debate":
        td["agent_team_discussion"] = True
    elif classification.agent in ("investment_strategy", "portfolio_health") and _TEAM_PHRASE.search(q):
        td["agent_team_discussion"] = True

    # retirement / multi-step plan profile — activated by financial_planning + planning language,
    # OR by numeric planner inputs even on a different route (age + income + horizon hint).
    has_planning_words = bool(_RETIREMENT_PHRASE.search(q))
    has_horizon_words = bool(re.search(r"\b\d+\s*(?:years?|yrs?)\b", ql))
    has_age_input = isinstance(user_context.get("age"), (int, float))
    has_income_input = isinstance(user_context.get("annual_income"), (int, float))
    is_planner_route = classification.agent == "financial_planning"
    if (is_planner_route and has_planning_words) or (
        has_planning_words and has_horizon_words and (has_age_input or has_income_input)
    ):
        td["retirement_planning"] = True
        td["requires_multi_agent"] = True
        doms = set(td["domains"])
        doms.update({"planning", "risk", "tax"})
        td["domains"] = sorted(doms)
        subs = list(td["sub_tasks"])
        for label in (
            "anchor_goal_inputs",
            "project_corpus_and_contributions",
            "stress_test_scenarios",
            "tax_account_framing",
            "synthesize_plan",
        ):
            if label not in subs:
                subs.append(label)
        td["sub_tasks"] = subs
        if not td.get("primary_theme"):
            td["primary_theme"] = "retirement_planning"

    if td.get("agent_team_discussion") and not td.get("discussion_team"):
        from .orchestration.team_planner import discussion_agent_ids_from_roles

        td["discussion_team"] = discussion_agent_ids_from_roles(
            q,
            classification.agent,
            dict(classification.entities or {}),
            user_context,
        )

    # LLMs somtimes keep tax+market domains from older turns; that locks tax_market_synthesis.
    # Strip ghost tax unless this line actually talks taxes (retirement block keeps tax on purpose).
    if not td.get("retirement_planning") and not _TAXISH.search(q):
        doms = set(td.get("domains") or [])
        if "tax" in doms:
            doms.discard("tax")
            td["domains"] = sorted(doms)
        if td.get("primary_theme") == "tax_timing_tradeoff":
            td["primary_theme"] = None

    # dont keep multi-agent tax desk flags if we only have one domain left and no panel ask
    if (
        td.get("requires_multi_agent")
        and not td.get("retirement_planning")
        and not td.get("agent_team_discussion")
        and classification.agent != "investment_debate"
        and len(td.get("domains") or []) < 2
    ):
        td["requires_multi_agent"] = False

    return replace(classification, task_decomposition=td)
