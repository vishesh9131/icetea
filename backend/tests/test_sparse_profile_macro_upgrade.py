from __future__ import annotations


def test_portfolio_health_macro_language_upgrades_to_full_panel():
    from icetea.pipeline import _collaborative_sparse_profile, _effective_collaboration_rounds

    prof = _collaborative_sparse_profile(
        "portfolio_health",
        entities={"tickers": []},
        query="I am getting nervous about recession headlines. Should I reduce risk?",
    )
    assert prof == "full"
    assert _effective_collaboration_rounds(prof, 3) >= 3

