"""Orchestrator-side specialist pick — who joins the panel + discussion thread."""
from __future__ import annotations

import re
from typing import Any

from .toolkits import portfolio_tools as port_tools

_PORTFOLIO_HINTS = re.compile(
    r"\b(portfolio|holdings|diversif|concentrat|allocation|position|my\s+stock)\b",
    re.I,
)
_MARKET_HINTS = re.compile(
    r"\b(market|momentum|quote|price|tape|ytd|return|chart|trading|stock\s+price)\b",
    re.I,
)
_TAX_HINTS = re.compile(
    r"\b(tax|taxes|capital\s+gains?|ltcg|stcg|harvest|taxable|lot)\b",
    re.I,
)
_RISK_HINTS = re.compile(
    r"\b(risk|volatil|drawdown|crash|downside|stress|worried\s+about\s+loss)\b",
    re.I,
)
_MOMENTUM_HINTS = re.compile(
    r"\b(momentum|trend|relative\s+strength|breakout|rally|fade)\b",
    re.I,
)

# default panel when the prompt doesnt spell out domains — still a team
_DEFAULT_TEAM: tuple[str, ...] = ("portfolio", "market", "risk", "momentum")


def select_specialist_roles(query: str, classification: dict[str, Any], user_context: dict[str, Any]) -> list[str]:
    """Return ordered specialist ids (subset of portfolio|market|tax_math|risk|momentum), max five."""
    q = (query or "").strip()
    roles: list[str] = []

    def add(role: str) -> None:
        if role not in roles:
            roles.append(role)

    if _PORTFOLIO_HINTS.search(q):
        add("portfolio")
    if _MARKET_HINTS.search(q):
        add("market")
    if _TAX_HINTS.search(q) and port_tools.list_positions(user_context):
        add("tax_math")
    if _RISK_HINTS.search(q):
        add("risk")
    if _MOMENTUM_HINTS.search(q):
        add("momentum")

    agent = str(classification.get("agent") or "")
    if agent == "investment_debate":
        for r in _DEFAULT_TEAM:
            add(r)
        if port_tools.list_positions(user_context):
            add("tax_math")
    elif agent == "portfolio_health" and not roles:
        add("portfolio")
        add("market")
        add("risk")
    elif agent == "investment_strategy" and not roles:
        for r in _DEFAULT_TEAM:
            add(r)

    if not roles:
        roles = list(_DEFAULT_TEAM)

    # cap keeps latency bounded
    return roles[:5]
