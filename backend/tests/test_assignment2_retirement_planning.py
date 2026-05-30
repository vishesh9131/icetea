"""Retirement / multi-step planning panel — math + supervisor + intent wiring."""
from __future__ import annotations

import asyncio
import math
from collections import deque

from icetea.classifier import Classification
from icetea.intent_decompose import merge_task_decomposition
from icetea.orchestration.supervisor import run_collaborative_supervisor
from icetea.orchestration.toolkits import planning_math as pm
from icetea.pipeline import _orchestration_profile
from icetea.session import SessionState


# ---------- math toolkit ----------

def test_future_value_annuity_basic_formula():
    # 100/mo for 12 months at 1% monthly = standard FV(annuity)
    pmt, r, n = 100.0, 0.01, 12
    expected = pmt * ((1 + r) ** n - 1) / r
    assert math.isclose(pm.future_value_annuity(pmt, r, n), expected, rel_tol=1e-9)


def test_future_value_annuity_zero_rate():
    assert pm.future_value_annuity(50.0, 0.0, 24) == 50.0 * 24


def test_infer_reference_income_age_brackets():
    lo30, hi30 = pm.infer_reference_pre_retirement_income_band(30)
    assert lo30 < hi30
    lo_none, hi_none = pm.infer_reference_pre_retirement_income_band(None)
    assert lo_none < hi_none


def test_required_contribution_already_on_track():
    # huge starting balance -> contribution should round to 0
    pmt = pm.required_contribution_monthly(
        target_fv=1_000_000.0,
        starting_balance=2_000_000.0,
        monthly_rate=0.005,
        months=120,
    )
    assert pmt == 0.0


def test_required_contribution_monotonic_in_rate():
    # higher monthly rate -> lower required contribution to hit same target
    low = pm.required_contribution_monthly(1_000_000.0, 0.0, 0.002, 240)
    high = pm.required_contribution_monthly(1_000_000.0, 0.0, 0.006, 240)
    assert low is not None and high is not None
    assert high < low


def test_build_retirement_bundle_produces_brackets_from_minimal_inputs():
    bundle = pm.build_retirement_bundle(
        query="I want to retire in 15 years with monthly passive income.",
        user_context={"age": 30, "annual_income": 120_000, "risk_profile": "moderate"},
    )
    sig = bundle["inputs_detected"]
    assert sig["horizon_years"] == 15
    assert sig["annual_income"] == 120_000
    ib = bundle["income_target_band"]
    # replacement ratio 60-80% of 120k -> 72k..96k annual
    assert ib["annual_low"] == 72_000
    assert ib["annual_high"] == 96_000
    cb = bundle["required_corpus"]
    assert cb["corpus_band_low"] is not None and cb["corpus_band_high"] is not None
    # 4% rule: 72k -> 1.8M is the band low across all WRs
    assert cb["corpus_band_low"] >= 1_700_000
    assert cb["corpus_band_high"] <= 3_500_000
    scs = bundle["contribution_solver"]["scenarios"]
    labels = [r["scenario"] for r in scs]
    assert labels == ["conservative", "base", "optimistic"]
    for r in scs:
        assert r["monthly_contribution_low"] is not None
        assert r["monthly_contribution_high"] is not None
        assert r["monthly_contribution_low"] <= r["monthly_contribution_high"]


def test_build_retirement_bundle_handles_missing_income_gracefully():
    bundle = pm.build_retirement_bundle(
        query="I want a plan to retire.",
        user_context={"age": 40, "risk_profile": "conservative"},
    )
    ib = bundle["income_target_band"]
    assert ib["source"] == "assumed_reference_pre_retirement_income_then_replacement"
    assert ib["annual_low"] is not None and ib["annual_high"] is not None
    cb = bundle["required_corpus"]
    assert cb["corpus_band_low"] is not None and cb["corpus_band_high"] is not None
    assert "horizon_years" in bundle["missing_inputs_for_higher_fidelity"]
    assert "stated_annual_or_monthly_income_optional_refinement" in bundle["missing_inputs_for_higher_fidelity"]


def test_render_summary_mentions_assumptions_when_data_present():
    bundle = pm.build_retirement_bundle(
        query="retire in 20 years with 5000/month",
        user_context={"annual_income": 90_000, "risk_profile": "moderate", "age": 35},
    )
    text = pm.render_planner_summary(bundle)
    assert "horizon" in text.lower() or "y horizon" in text.lower()
    assert "withdrawal" in text.lower() or "%" in text
    assert "Deterministic" in text


# ---------- intent_decompose + pipeline profile ----------

def _make_classification(agent: str, query_for_td: str | None = None) -> Classification:
    return Classification(
        agent=agent,
        intent="planning" if agent == "financial_planning" else None,
        entities={},
        confidence=0.9,
        fallback_used=False,
        error=None,
        safety_verdict=None,
        task_decomposition={},
    )


def test_intent_decompose_sets_retirement_profile_on_planner_route():
    cls = _make_classification("financial_planning")
    q = "I want to retire in 15 years with monthly passive income."
    merged = merge_task_decomposition(
        cls,
        q,
        {"age": 30, "annual_income": 120_000, "risk_profile": "moderate"},
    )
    td = merged.task_decomposition or {}
    assert td.get("retirement_planning") is True
    assert td.get("requires_multi_agent") is True
    assert "planning" in td.get("domains") or []
    assert _orchestration_profile(merged, query=q) == "retirement_planning"


def test_intent_decompose_sets_retirement_profile_when_numeric_inputs_only():
    # Even on a non-planner route, if planning words + horizon + age/income inputs are present
    cls = _make_classification("general_query")
    q = "Make me a retirement plan for the next 25 years."
    merged = merge_task_decomposition(
        cls,
        q,
        {"age": 35, "annual_income": 80_000, "risk_profile": "moderate"},
    )
    td = merged.task_decomposition or {}
    assert td.get("retirement_planning") is True
    assert td.get("requires_multi_agent") is True
    assert _orchestration_profile(merged, query=q) == "retirement_planning"


def test_house_horizon_triggers_retirement_merge_on_planner_route():
    cls = _make_classification("financial_planning")
    q = "I want to buy a house in 4 years."
    merged = merge_task_decomposition(cls, q, {"risk_profile": "moderate"})
    assert merged.task_decomposition.get("retirement_planning") is True


def test_intent_decompose_skips_retirement_profile_for_unrelated_questions():
    cls = _make_classification("portfolio_health")
    merged = merge_task_decomposition(
        cls,
        "How is my portfolio doing today?",
        {"age": 30, "annual_income": 120_000, "positions": [{"ticker": "NVDA", "quantity": 5}]},
    )
    td = merged.task_decomposition or {}
    assert not td.get("retirement_planning")


def test_merge_strips_ghost_tax_domain_when_turn_has_no_tax_language():
    cls = Classification(
        agent="investment_strategy",
        intent="preferences",
        entities={"tickers": ["NVDA"]},
        confidence=0.8,
        safety_verdict={"category": None, "rationale": ""},
        task_decomposition={
            "primary_theme": "tax_timing_tradeoff",
            "sub_tasks": [],
            "domains": ["tax", "market", "strategy"],
            "requires_multi_agent": True,
            "discussion_team": [],
            "agent_team_discussion": False,
        },
    )
    merged = merge_task_decomposition(
        cls,
        "I never invest in gambling or tobacco companies.",
        {"positions": [{"ticker": "NVDA", "quantity": 80}]},
    )
    doms = merged.task_decomposition.get("domains") or []
    assert "tax" not in doms
    assert merged.task_decomposition.get("primary_theme") != "tax_timing_tradeoff"


def test_orchestration_tax_market_only_when_query_has_tax_and_trade_words():
    cls = Classification(
        agent="investment_strategy",
        intent="sell",
        entities={"tickers": ["NVDA"], "action": "sell"},
        confidence=0.9,
        safety_verdict={"category": None, "rationale": ""},
        task_decomposition={
            "primary_theme": "tax_timing_tradeoff",
            "sub_tasks": [],
            "domains": ["tax", "market", "strategy"],
            "requires_multi_agent": True,
            "discussion_team": [],
            "agent_team_discussion": False,
        },
    )
    assert (
        _orchestration_profile(
            cls,
            query="If I sell NVDA should I worry about capital gains taxes this year?",
        )
        == "tax_market_synthesis"
    )
    assert _orchestration_profile(cls, query="What are the biggest risks in my strategy?") is None


# ---------- supervisor: actually fires 5 rounds ----------

def _collect_supervisor(async_gen):
    out: list = []

    async def _run():
        async for x in async_gen:
            out.append(x)

    asyncio.run(_run())
    return out


def test_retirement_supervisor_runs_five_rounds_with_numbers():
    state = SessionState(session_id="s_retire", turns=deque(maxlen=16))
    classification = {
        "agent": "financial_planning",
        "intent": "planning",
        "entities": {},
        "orchestration_profile": "retirement_planning",
    }
    hist = [{"role": "user", "content": "I want to retire in 15 years with monthly passive income."}]
    events = _collect_supervisor(
        run_collaborative_supervisor(
            query="I want to retire in 15 years with monthly passive income.",
            session_id="s_retire",
            user_context={"age": 30, "annual_income": 120_000, "risk_profile": "moderate"},
            conversation_history=hist,
            state=state,
            classification=classification,
            rounds=3,
        )
    )
    disc = [e for e in events if e.get("type") == "meta" and e.get("stage") == "agent_discussion"]
    assert [e.get("agent") for e in disc] == [
        "planner",
        "projection",
        "scenario",
        "tax_account",
        "synthesis",
    ]
    assert len(state.discussion_log) == 5
    structured = next(e for e in events if e.get("type") == "structured")
    payload = structured["payload"]
    assert payload["agent"] == "multiagent_orchestrator"
    assert payload["collaboration_meta"]["mode"] == "retirement_planning"
    bundle = payload.get("retirement_plan_bundle") or {}
    assert bundle.get("required_corpus", {}).get("corpus_band_low") is not None
    msg = payload["message"]
    # Final message should contain actual numbers and labelled assumptions
    assert "withdrawal" in msg.lower() or "corpus" in msg.lower()
    assert "Deterministic" in msg or "deterministic" in msg


def test_retirement_supervisor_brackets_even_when_income_missing():
    state = SessionState(session_id="s_retire_part", turns=deque(maxlen=16))
    classification = {
        "agent": "financial_planning",
        "intent": "planning",
        "entities": {},
        "orchestration_profile": "retirement_planning",
    }
    events = _collect_supervisor(
        run_collaborative_supervisor(
            query="I want to plan retirement in 20 years.",
            session_id="s_retire_part",
            user_context={"age": 40, "risk_profile": "conservative"},
            conversation_history=[],
            state=state,
            classification=classification,
            rounds=3,
        )
    )
    disc = [e for e in events if e.get("type") == "meta" and e.get("stage") == "agent_discussion"]
    # All 5 rounds STILL run — the panel reports what is needed instead of bailing.
    assert len(disc) == 5
    payload = next(e for e in events if e.get("type") == "structured")["payload"]
    assert (payload.get("retirement_plan_bundle") or {}).get("required_corpus", {}).get("corpus_band_low") is not None
    msg = payload["message"].lower()
    miss = payload.get("retirement_plan_bundle", {}).get("missing_inputs_for_higher_fidelity", [])
    assert "stated_annual_or_monthly_income_optional_refinement" in miss
    assert (
        "corpus" in msg
        or "withdrawal" in msg
        or "monthly contribution" in msg
        or "/mo" in msg
        or "projection" in msg
    )
