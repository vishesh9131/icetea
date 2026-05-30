"""
Risk Assessment agent: deterministic math + streaming wrapper sanity.

We deliberately bypass the real market_data calls — the agent must produce
a sensible structured payload on a bare portfolio even when prices arent
available (which is the test-mode default).
"""
from __future__ import annotations

import pytest

from icetea.agents.registry import get_agent, is_implemented
from icetea.agents.risk_assessment import (
    RiskAssessmentAgent,
    _parse_market_shocks,
    assess_risk,
)


def test_registry_picks_up_risk_assessment():
    a = get_agent("risk_assessment")
    assert isinstance(a, RiskAssessmentAgent)
    assert is_implemented("risk_assessment") is True


@pytest.mark.parametrize(
    "query,expected",
    [
        ("Stress test my portfolio if the market drops 30% next quarter.", [30]),
        ("What if we get a 20% sell-off and then a 10% drop?", [20, 10]),
        ("Run a -25% market shock please.", [25]),
        ("just give me a risk read", []),
        ("no numbers", []),
    ],
)
def test_parse_market_shocks(query, expected):
    assert _parse_market_shocks(query) == expected


def test_assess_risk_empty_portfolio_returns_build_mode():
    out = assess_risk({"positions": []}, query="stress test me")
    assert out["agent"] == "risk_assessment"
    assert out["mode"] == "build"
    assert out["disclaimer"]
    assert out["scenarios"] == []


def test_assess_risk_concentrated_book_flags_high_and_orders_contributors():
    out = assess_risk(
        {
            "positions": [
                {"ticker": "NVDA", "quantity": 180, "avg_cost": 218.40, "currency": "USD"},
                {"ticker": "VTI", "quantity": 25, "avg_cost": 218.50, "currency": "USD"},
                {"ticker": "AAPL", "quantity": 8, "avg_cost": 168.20, "currency": "USD"},
            ],
            "risk_profile": "moderate",
        },
        query="if the market drops 30% what happens",
    )
    assert out["concentration_risk"]["flag"] in ("high", "warning")
    assert out["concentration_risk"]["top_holding"] == "NVDA"
    # NVDA is biggest weight, must lead the contributor list
    assert out["top_risk_contributors"][0]["ticker"] == "NVDA"
    # We asked for a 30% shock — must be the (only) scenario, not the defaults.
    shocks = [s["market_shock_pct"] for s in out["scenarios"]]
    assert shocks == [-30]
    # beta-proxy weighting should push the portfolio drop > the market shock
    assert out["scenarios"][0]["portfolio_estimated_drop_pct"] <= -30.0


def test_assess_risk_defensive_book_lowers_beta():
    out = assess_risk(
        {
            "positions": [
                {"ticker": "BND", "quantity": 200, "avg_cost": 72.10, "currency": "USD"},
                {"ticker": "VYM", "quantity": 100, "avg_cost": 102.10, "currency": "USD"},
            ],
            "risk_profile": "conservative",
        },
        query="how bad is the worst case",
    )
    beta = out["portfolio_beta_proxy"]
    assert beta is not None and beta < 0.9
    # Defaults kick in (-10/-20/-30)
    assert [s["market_shock_pct"] for s in out["scenarios"]] == [-10, -20, -30]


def test_assess_risk_currency_exposure_picks_up_non_base():
    out = assess_risk(
        {
            "positions": [
                {"ticker": "AAPL", "quantity": 10, "avg_cost": 150, "currency": "USD"},
                {"ticker": "ASML.AS", "quantity": 5, "avg_cost": 600, "currency": "EUR"},
                {"ticker": "HSBA.L", "quantity": 200, "avg_cost": 6, "currency": "GBP"},
            ],
        },
        query="how risky am i",
    )
    cur = out["currency_exposure"]
    assert "USD" in cur["breakdown"]
    assert cur["flag"] in ("moderate", "high")


async def test_streaming_run_yields_data_then_structured_when_no_llm():
    agent = RiskAssessmentAgent()

    events = []
    async for ev in agent.run(
        query="if the market drops 25% what happens",
        user_context={
            "positions": [
                {"ticker": "NVDA", "quantity": 100, "avg_cost": 200, "currency": "USD"},
            ],
        },
        classification={"agent": "risk_assessment", "intent": "stress", "entities": {}},
        llm=None,
        conversation_history=[],
    ):
        events.append(ev)
    types = [e["type"] for e in events]
    assert "data" in types
    assert types[-1] == "structured"
    payload = events[-1]["payload"]
    assert payload["agent"] == "risk_assessment"
    assert payload.get("disclaimer")
    assert payload.get("scenarios") and payload["scenarios"][0]["market_shock_pct"] == -25
