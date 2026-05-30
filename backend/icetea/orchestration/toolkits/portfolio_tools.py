"""Portfolio-side tools (holdings, concentration, profile hints)."""
from __future__ import annotations

from typing import Any


def _position_notional_usd(p: dict[str, Any]) -> float | None:
    """Best-effort USD notion from quantity * price or explicit market_value."""
    qty = float(p.get("quantity") or 0)
    if qty <= 0:
        return None
    for key in ("last_price", "last_px", "mark", "price", "nav", "close"):
        px = p.get(key)
        if isinstance(px, (int, float)) and float(px) > 0:
            return qty * float(px)
    for key in ("avg_cost", "average_cost", "cost_basis_per_share"):
        ac = p.get(key)
        if isinstance(ac, (int, float)) and float(ac) > 0:
            return qty * float(ac)
    mv = p.get("market_value") or p.get("notional") or p.get("value")
    if isinstance(mv, (int, float)) and float(mv) > 0:
        return float(mv)
    return None


def list_positions(user_context: dict[str, Any]) -> list[dict[str, Any]]:
    raw = user_context.get("positions") or []
    out: list[dict[str, Any]] = []
    for p in raw:
        if isinstance(p, dict):
            out.append(p)
    return out


def summarize_allocation(user_context: dict[str, Any]) -> dict[str, Any]:
    positions = list_positions(user_context)
    if not positions:
        return {"mode": "empty", "lines": ["No positions on file for this user."], "position_count": 0}
    notionals = [_position_notional_usd(p) for p in positions]
    use_dollar = all(n is not None and n > 0 for n in notionals)
    total_qty = sum(float(p.get("quantity") or 0) for p in positions)
    lines: list[str] = []
    weights: list[float] = []
    if use_dollar:
        total_n = float(sum(notionals))  # type: ignore[arg-type]
        for p, n in zip(positions, notionals, strict=True):
            t = str(p.get("ticker") or "?")
            q = float(p.get("quantity") or 0)
            w = (float(n) / total_n) if total_n > 0 else 0.0
            lines.append(f"{t}: qty={q:.4g}, ~{w * 100:.1f}% of book (notional)")
            weights.append(max(0.0, w))
        basis = "notional_usd_proxy"
    else:
        for p in positions:
            t = str(p.get("ticker") or "?")
            q = float(p.get("quantity") or 0)
            share = (q / total_qty * 100.0) if total_qty > 0 else 0.0
            lines.append(f"{t}: qty={q:.4g}, ~{share:.1f}% of share count (no prices on lines — weak for concentration)")
            weights.append(max(0.0, share / 100.0))
        basis = "share_count_fallback"
    hhi = sum(s * s for s in weights) if weights else 0.0
    eff_n = (1.0 / hhi) if hhi > 0 else (float(len(weights)) if weights else 0.0)
    top2 = sorted(weights, reverse=True)[:2]
    top2_pct = round(sum(top2) * 100.0, 1) if top2 else 0.0
    return {
        "mode": "holdings",
        "lines": lines,
        "position_count": len(positions),
        "concentration_basis": basis,
        "hhi": round(hhi, 4),
        "effective_num_holdings": round(eff_n, 2),
        "top2_weight_pct": top2_pct,
    }


def flag_concentration(user_context: dict[str, Any]) -> dict[str, Any]:
    positions = list_positions(user_context)
    if not positions:
        return {"flag": "n/a", "detail": "nothing held"}
    notionals = [_position_notional_usd(p) for p in positions]
    use_dollar = all(n is not None and n > 0 for n in notionals)
    if use_dollar:
        pairs = [(p, float(n)) for p, n in zip(positions, notionals, strict=True)]  # type: ignore[arg-type]
        top_p, top_n = max(pairs, key=lambda x: x[1])
        top_t = str(top_p.get("ticker") or "?")
        total_n = sum(float(n) for _, n in pairs)
        pct = (top_n / total_n * 100.0) if total_n > 0 else 0.0
        sorted_n = sorted((n for _, n in pairs), reverse=True)
        top2_n = sum(sorted_n[:2]) if sorted_n else 0.0
        top2_pct = (top2_n / total_n * 100.0) if total_n > 0 else 0.0
        basis = "notional_usd_proxy"
        flag = "warning" if pct >= 45 else "ok"
        return {
            "flag": flag,
            "top_holding": top_t,
            "top_notional_pct": round(pct, 1),
            "top2_notional_pct": round(top2_pct, 1),
            "top_share_pct": round(pct, 1),
            "top2_share_pct": round(top2_pct, 1),
            "concentration_basis": basis,
            "position_count": len(positions),
            "note": "notional from position prices / avg_cost / market_value when present",
        }
    top = max(positions, key=lambda p: float(p.get("quantity") or 0))
    top_t = str(top.get("ticker") or "?")
    total_q = sum(float(p.get("quantity") or 0) for p in positions)
    top_q = float(top.get("quantity") or 0)
    pct = (top_q / total_q * 100.0) if total_q > 0 else 0.0
    flag = "warning" if pct >= 45 else "ok"
    sorted_q = sorted((float(p.get("quantity") or 0) for p in positions), reverse=True)
    top2_q = sum(sorted_q[:2]) if sorted_q else 0.0
    top2_pct = (top2_q / total_q * 100.0) if total_q > 0 else 0.0
    return {
        "flag": flag,
        "top_holding": top_t,
        "top_share_pct": round(pct, 1),
        "top2_share_pct": round(top2_pct, 1),
        "concentration_basis": "share_count_fallback",
        "position_count": len(positions),
        "note": "share-count proxy; add last_price or market_value on positions for $ weights",
    }


def match_tickers_to_positions(user_context: dict[str, Any], tickers: list[str]) -> dict[str, Any]:
    tickers_u = [str(t).strip().upper() for t in tickers if str(t).strip()]
    held = {str(p.get("ticker") or "").strip().upper() for p in list_positions(user_context)}
    matched = [t for t in tickers_u if t in held]
    missing = [t for t in tickers_u if t not in held]
    return {"matched_in_portfolio": matched, "not_held": missing}


def snapshot_risk_profile(user_context: dict[str, Any]) -> dict[str, Any]:
    return {
        "risk_profile": user_context.get("risk_profile"),
        "base_currency": user_context.get("base_currency"),
        "user_id": user_context.get("user_id"),
    }
