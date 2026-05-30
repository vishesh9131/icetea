"""Dynamic agent-team discussion orchestration (agent-to-agent thread + synthesis)."""
from __future__ import annotations

import asyncio

import pytest

from icetea.pipeline import process_query


def _collect(events):
    out = []

    async def _run():
        async for e in events:
            out.append(e)

    asyncio.run(_run())
    return out


def test_agent_team_discussion_runs_for_investment_debate_collaborative(fake_llm):
    out = _collect(
        process_query(
            query="Bull vs bear on NVDA over five years — weigh fundamentals and risk.",
            session_id="sess_agent_team_debate",
            user_context={
                "user_id": "u_debate",
                "positions": [{"ticker": "NVDA", "quantity": 5, "avg_cost": 100.0, "currency": "USD"}],
            },
            llm=fake_llm,
            collaborative=True,
        )
    )
    metas = [e for e in out if e.get("type") == "meta"]
    start = next(e for e in metas if e.get("stage") == "collaborative_start")
    assert start.get("orchestration_profile") == "agent_team_discussion"
    assert "selected_team" in start
    structured = next(e for e in out if e.get("type") == "structured")
    payload = structured["payload"]
    assert payload.get("agent_thread_transcript")
    assert len(payload["agent_thread_transcript"]) >= 4  # 2 cycles * min 2 speakers typical team
    assert payload.get("collaboration_meta", {}).get("mode") == "agent_team_synthesis"


def test_agent_team_keyword_on_strategy_collaborative(fake_llm):
    out = _collect(
        process_query(
            query="Should I trim tech — lets have a team discussion with multiple perspectives on risk and momentum.",
            session_id="sess_agent_team_kw",
            user_context={
                "user_id": "u1",
                "positions": [
                    {"ticker": "NVDA", "quantity": 5, "avg_cost": 100.0, "currency": "USD"},
                    {"ticker": "QQQ", "quantity": 2, "avg_cost": 300.0, "currency": "USD"},
                ],
            },
            llm=fake_llm,
            collaborative=True,
        )
    )
    start = next(e for e in out if e.get("type") == "meta" and e.get("stage") == "collaborative_start")
    assert start.get("orchestration_profile") == "agent_team_discussion"
