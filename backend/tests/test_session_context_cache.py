from __future__ import annotations


def test_pipeline_hydrates_positions_from_session_cache():
    # This is the bug in "real-user-journey": user gives positions once,
    # then asks a follow-up without resending them.
    from icetea.pipeline import _hydrate_user_context_from_state
    from icetea.session import SessionState

    state = SessionState(session_id="s1", turns=__import__("collections").deque(maxlen=16))
    state.context_cache = {
        "user_id": "u10",
        "risk_profile": "moderate",
        "positions": [{"ticker": "NVDA", "quantity": 50}, {"ticker": "QQQ", "quantity": 40}],
    }

    hydrated = _hydrate_user_context_from_state({"user_id": "u10"}, state)
    assert hydrated.get("positions"), "expected cached positions to be injected"
    assert hydrated["positions"][0]["ticker"] == "NVDA"


def test_pipeline_does_not_overwrite_explicit_positions():
    from icetea.pipeline import _hydrate_user_context_from_state
    from icetea.session import SessionState

    state = SessionState(session_id="s1", turns=__import__("collections").deque(maxlen=16))
    state.context_cache = {"positions": [{"ticker": "OLD", "quantity": 1}]}

    req_ctx = {"positions": [{"ticker": "NEW", "quantity": 2}]}
    hydrated = _hydrate_user_context_from_state(req_ctx, state)
    assert hydrated["positions"][0]["ticker"] == "NEW"

