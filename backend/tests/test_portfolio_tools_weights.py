from __future__ import annotations


def test_summarize_prefers_notional_when_every_line_has_price():
    from icetea.orchestration.toolkits import portfolio_tools as pt

    ctx = {
        "positions": [
            {"ticker": "NVDA", "quantity": 80, "last_price": 219.0},
            {"ticker": "QQQ", "quantity": 40, "last_price": 350.0},
        ]
    }
    out = pt.summarize_allocation(ctx)
    assert out["concentration_basis"] == "notional_usd_proxy"
    joined = " ".join(out["lines"])
    assert "notional" in joined.lower()
    nvda_n = 80 * 219.0
    total = nvda_n + 40 * 350.0
    exp_pct = round(nvda_n / total * 100.0, 1)
    assert str(exp_pct) in joined or str(round(exp_pct)) in joined


def test_flag_concentration_uses_notional_ranking_when_prices_present():
    from icetea.orchestration.toolkits import portfolio_tools as pt

    ctx = {
        "positions": [
            {"ticker": "NVDA", "quantity": 80, "last_price": 219.0},
            {"ticker": "QQQ", "quantity": 40, "last_price": 350.0},
        ]
    }
    fc = pt.flag_concentration(ctx)
    assert fc.get("concentration_basis") == "notional_usd_proxy"
    assert fc.get("top_notional_pct") is not None
    assert fc["top_holding"] == "NVDA"
