"""
Stub agents.

The router must work end-to-end even for agents we havent shipped. So
each unimplemented agent emits a structured 'not implemented' payload
plus a single human-readable line for the SSE narrative. No exceptions,
no errors.
"""
from __future__ import annotations

from typing import Any, AsyncIterator


_NOT_IMPLEMENTED_FRIENDLY = {
    "market_research":        "I'd normally pull live market data, news, and a quick read on this one — but the market research agent isn't wired up in this build yet.",
    "investment_strategy":    "Strategy questions go through a dedicated agent that weighs your risk profile and current allocation — not implemented in this build.",
    "financial_planning":     "Planning conversations (retirement, FIRE, education) run through a dedicated planner — not implemented in this build.",
    "financial_calculator":   "Numerical calculations (DCA, mortgage, future value, FX) are handled by a dedicated calculator — not implemented in this build.",
    "risk_assessment":        "Risk metrics like beta, drawdown, and stress tests come from a dedicated risk agent — not implemented in this build.",
    "product_recommendation": "Product recommendations are handled by a dedicated agent that considers fees, fit, and your profile — not implemented in this build.",
    "predictive_analysis":    "Forecasting questions go through a forecasting agent — not implemented in this build.",
    "customer_support":       "Account and platform questions are handled by support — not implemented in this build.",
    "general_query":          "I can handle simple definitions and small talk in this build, but the full educational agent isn't wired up.",
    "portfolio_query":        "Portfolio lookup is handled by a dedicated query agent — not implemented in this build.",
}


class StubAgent:
    def __init__(self, agent_name: str) -> None:
        self.name = agent_name

    async def run(
        self,
        *,
        query: str,
        user_context: dict[str, Any],
        classification: dict[str, Any],
        llm: Any | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        message = _NOT_IMPLEMENTED_FRIENDLY.get(
            self.name,
            f"The {self.name} agent isn't implemented in this build.",
        )
        yield {"type": "data", "delta": message}
        yield {
            "type": "structured",
            "payload": {
                "agent": self.name,
                "implemented": False,
                "intent": classification.get("intent"),
                "entities": classification.get("entities", {}),
                "message": message,
            },
        }
