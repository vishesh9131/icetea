"""Duplicate-query guard: repeated back-to-back asks should not rerun classifier/agent."""
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


def test_duplicate_query_short_circuits_and_reuses_prior_answer(fake_llm):
    sid = "sess_dup_guard"
    q = "Optimize my portfolio for moderate growth."
    user = {"user_id": "u1", "positions": [{"ticker": "AAPL", "quantity": 1}]}

    # First call uses normal pipeline (classifier runs).
    out1 = _collect(process_query(query=q, session_id=sid, user_context=user, llm=fake_llm, collaborative=True))
    assert any(e.get("type") == "done" for e in out1)
    a1 = "".join(e.get("delta", "") for e in out1 if e.get("type") == "data").strip()
    assert a1

    # Second call with same query should short-circuit BEFORE classifier.
    def _boom(_msgs):
        pytest.fail("classifier should not run for exact duplicate query")

    out2 = _collect(process_query(query=q, session_id=sid, user_context=user, llm=_boom, collaborative=True))
    meta = next(e for e in out2 if e.get("type") == "meta" and e.get("stage") == "duplicate_query_short_circuit")
    assert meta.get("reused_prior_answer") is True
    a2 = "".join(e.get("delta", "") for e in out2 if e.get("type") == "data").strip()
    assert a2 == a1

