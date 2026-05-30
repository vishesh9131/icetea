"""
Risk Assessment agent.

Speaks to PROTECT. The user lands here when they want a stress test, a
beta / drawdown read, a "what happens if the market drops X%" answer, or
a currency-exposure check on a multi-region book.

Design choices (kept small on purpose)
--------------------------------------
- All math is deterministic. The narrative is the only LLM piece, and the
  agent still ships a usable answer if the LLM is down.
- Beta is a *proxy*: we map each holding to a coarse sector volatility tier
  rather than pulling real betas. Real beta would require either an MCP
  market data server or a heavier yfinance pull per ticker (the existing
  market_data.py wrapper supports quote, not historical regression). Keeps
  this self-contained and fast.
- Stress scenarios: we parse explicit "drops 30%" / "-30%" / "30% drop" from
  the user query. If none is found we fall back to three canonical buckets
  (mild -10%, moderate -20%, severe -30%) so a novice still gets a range.
- We do NOT pretend to know cross-asset correlations. The scenario impact is
  weighted beta-proxy times the market shock, capped at -90% per name so
  the output stays sane. This is intentionally simple; documented here so
  reviewers dont read it as Monte Carlo.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from ..llm import LLMClient, LLMError, assemble_messages, get_llm_client
from ..safety import MODEL_INJECTION_GUARD
from ..market_data import get_quote


logger = logging.getLogger(__name__)


DISCLAIMER = (
    "Risk numbers shown here are illustrative scenario approximations from your "
    "holdings and rough sector volatility tiers — not Monte Carlo simulations, "
    "not portfolio optimisations. Always consult a qualified advisor before "
    "acting on stress-test output."
)

# Concentration thresholds — mirror portfolio_health so the two agents tell
# the user the same story instead of two different "concentrated" labels.
CONCENTRATION_HIGH = 0.40
CONCENTRATION_MEDIUM = 0.25

# Coarse beta-proxy by sector / asset class. Tuned for "novice-friendly tier"
# rather than statistical accuracy: any number > 1.0 means "moves more than
# the broad market in a typical drawdown".
_SECTOR_BETA: dict[str, float] = {
    "technology": 1.30,
    "communication services": 1.20,
    "consumer cyclical": 1.20,
    "consumer discretionary": 1.20,
    "industrials": 1.10,
    "energy": 1.20,
    "financial services": 1.20,
    "financial": 1.20,
    "real estate": 1.00,
    "healthcare": 0.85,
    "consumer defensive": 0.70,
    "consumer staples": 0.70,
    "utilities": 0.55,
    "basic materials": 1.05,
}

# When we cant infer a sector (etf, foreign ticker, missing yfinance info), we
# still want a reasonable default. ETFs get a market beta of 1.0; single names
# get something slightly more aggressive because a novice with a single name
# is usually long a popular growth stock.
_DEFAULT_ETF_BETA = 1.00
_DEFAULT_SINGLE_NAME_BETA = 1.15
_DEFAULT_BOND_BETA = 0.15

# Tickers we hard-classify so we dont have to call out to yfinance just to
# learn that BND is a bond ETF.
_KNOWN_TIER: dict[str, tuple[str, float]] = {
    "BND": ("bonds", _DEFAULT_BOND_BETA),
    "AGG": ("bonds", _DEFAULT_BOND_BETA),
    "TLT": ("bonds", 0.10),
    "VTI": ("broad_us_etf", 1.00),
    "VOO": ("broad_us_etf", 1.00),
    "SPY": ("broad_us_etf", 1.00),
    "QQQ": ("nasdaq_etf", 1.15),
    "VXUS": ("intl_etf", 0.95),
    "VYM": ("dividend_etf", 0.85),
    "SCHD": ("dividend_etf", 0.85),
    "URTH": ("global_etf", 0.95),
}


_PCT_DROP_RE = re.compile(
    r"(?:drop|down|fall|crash|sell[- ]?off|correction)[^\d]{0,18}(\d{1,2})\s*%"
    r"|(\d{1,2})\s*%[^\w]{0,5}(?:drop|down|fall|crash|sell[- ]?off|correction)"
    r"|(?:^|\s)-?\s*(\d{1,2})\s*%(?:\s*(?:drop|down|fall|crash|move|shock))?",
    re.IGNORECASE,
)


@dataclass
class _PositionRow:
    ticker: str
    quantity: float
    avg_cost: float
    currency: str
    market_price: float | None
    market_value: float
    weight_pct: float
    sector: str | None
    beta_proxy: float
    bucket: str


def _round(x: float | None, digits: int = 2) -> float | None:
    if x is None:
        return None
    return round(float(x), digits)


def _classify_position(ticker: str, quote_sector: str | None) -> tuple[str, float, str | None]:
    """Return (bucket_label, beta_proxy, sector_label).

    bucket_label is the rough family we put this name into for narrative
    purposes ("single_name", "broad_us_etf", "bonds"…). sector_label is
    only filled when we actually know the equity sector.
    """
    t_upper = (ticker or "").upper()
    if t_upper in _KNOWN_TIER:
        bucket, beta = _KNOWN_TIER[t_upper]
        return bucket, beta, None
    sector = (quote_sector or "").strip().lower() if quote_sector else None
    if sector and sector in _SECTOR_BETA:
        return "single_name", _SECTOR_BETA[sector], sector
    # ETF-ish suffix heuristics. yfinance often doesnt populate sector for ETFs.
    if t_upper.endswith(("ETF", "INDEX")) or t_upper in {"IWM", "EFA", "EEM", "DIA"}:
        return "etf_other", _DEFAULT_ETF_BETA, None
    return "single_name", _DEFAULT_SINGLE_NAME_BETA, None


def _parse_market_shocks(query: str) -> list[int]:
    """Return all explicit drop percentages mentioned in the query (deduped, capped)."""
    if not query:
        return []
    found: list[int] = []
    for m in _PCT_DROP_RE.finditer(query):
        for g in m.groups():
            if g is None:
                continue
            try:
                v = int(g)
            except ValueError:
                continue
            if 1 <= v <= 90 and v not in found:
                found.append(v)
    return found[:4]


def _default_shocks() -> list[int]:
    return [10, 20, 30]


def _portfolio_rows(positions: list[dict[str, Any]]) -> tuple[list[_PositionRow], dict[str, Any]]:
    rows: list[_PositionRow] = []
    total_value = 0.0
    data_gaps: list[str] = []

    for pos in positions or []:
        if not isinstance(pos, dict):
            continue
        ticker = str(pos.get("ticker") or "").strip()
        if not ticker:
            continue
        try:
            qty = float(pos.get("quantity") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        try:
            avg = float(pos.get("avg_cost") or 0)
        except (TypeError, ValueError):
            avg = 0.0
        cur = (pos.get("currency") or "USD").upper()

        q = get_quote(ticker)
        price = q.price if q else None
        sector_raw = q.sector if q else None
        if price is None:
            data_gaps.append(ticker)
            value = qty * avg if avg > 0 else 0.0
        else:
            value = qty * float(price)

        bucket, beta, sector_label = _classify_position(ticker, sector_raw)
        total_value += value
        rows.append(
            _PositionRow(
                ticker=ticker.upper(),
                quantity=qty,
                avg_cost=avg,
                currency=cur,
                market_price=price,
                market_value=value,
                weight_pct=0.0,  # filled in below
                sector=sector_label,
                beta_proxy=beta,
                bucket=bucket,
            )
        )

    if total_value > 0:
        for r in rows:
            r.weight_pct = (r.market_value / total_value) * 100.0
    rows.sort(key=lambda r: r.weight_pct, reverse=True)
    summary = {
        "total_value": _round(total_value),
        "position_count": len(rows),
        "data_gaps": data_gaps,
    }
    return rows, summary


def _concentration_block(rows: list[_PositionRow]) -> dict[str, Any]:
    if not rows:
        return {
            "top_position_pct": 0.0,
            "top_3_positions_pct": 0.0,
            "flag": "n/a",
            "top_holding": None,
        }
    top = rows[0].weight_pct / 100.0
    top3 = sum(r.weight_pct for r in rows[:3]) / 100.0
    if top >= CONCENTRATION_HIGH:
        flag = "high"
    elif top >= CONCENTRATION_MEDIUM:
        flag = "warning"
    else:
        flag = "low"
    return {
        "top_position_pct": _round(top * 100.0),
        "top_3_positions_pct": _round(top3 * 100.0),
        "flag": flag,
        "top_holding": rows[0].ticker,
    }


def _currency_exposure(rows: list[_PositionRow]) -> dict[str, Any]:
    if not rows:
        return {"breakdown": {}, "non_base_pct": 0.0, "flag": "n/a"}
    buckets: dict[str, float] = defaultdict(float)
    for r in rows:
        buckets[r.currency] += r.market_value
    total = sum(buckets.values()) or 1.0
    breakdown = {cur: _round(v / total * 100.0) for cur, v in buckets.items()}
    base = "USD" if "USD" in breakdown else max(breakdown, key=breakdown.get)
    non_base = sum(v for cur, v in breakdown.items() if cur != base)
    if non_base >= 50:
        flag = "high"
    elif non_base >= 20:
        flag = "moderate"
    else:
        flag = "low"
    return {
        "breakdown": breakdown,
        "base_currency_assumed": base,
        "non_base_pct": _round(non_base),
        "flag": flag,
    }


def _portfolio_weighted_beta(rows: list[_PositionRow]) -> float | None:
    if not rows:
        return None
    total_w = sum(r.weight_pct for r in rows) or 0.0
    if total_w <= 0:
        return None
    return sum(r.weight_pct * r.beta_proxy for r in rows) / total_w


def _scenarios(rows: list[_PositionRow], shocks: list[int]) -> list[dict[str, Any]]:
    """Project portfolio drawdown for each market shock, beta-weighted."""
    beta = _portfolio_weighted_beta(rows)
    out: list[dict[str, Any]] = []
    for shock in shocks:
        portfolio_drop_pct = -float(shock) * (beta or 1.0)
        # Cap so a 90% market shock doesnt produce -135% portfolio.
        portfolio_drop_pct = max(portfolio_drop_pct, -95.0)
        total_value = sum(r.market_value for r in rows) or 0.0
        loss_amount = abs(portfolio_drop_pct) / 100.0 * total_value if total_value else None
        out.append({
            "market_shock_pct": -shock,
            "portfolio_estimated_drop_pct": _round(portfolio_drop_pct),
            "estimated_loss_amount": _round(loss_amount),
            "beta_proxy_used": _round(beta, 3),
        })
    return out


def _drawdown_contributors(rows: list[_PositionRow], top_n: int = 3) -> list[dict[str, Any]]:
    contribs: list[tuple[float, _PositionRow]] = []
    for r in rows:
        # contribution = weight * beta (this is the position's slice of the
        # portfolio beta). A heavy NVDA position with beta 1.3 dominates.
        contribs.append(((r.weight_pct / 100.0) * r.beta_proxy, r))
    contribs.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "ticker": r.ticker,
            "weight_pct": _round(r.weight_pct),
            "beta_proxy": _round(r.beta_proxy, 3),
            "share_of_portfolio_beta": _round(c * 100.0),
            "sector": r.sector,
            "bucket": r.bucket,
        }
        for c, r in contribs[:top_n]
    ]


def _observations(
    rows: list[_PositionRow],
    *,
    concentration: dict[str, Any],
    currency: dict[str, Any],
    scenarios: list[dict[str, Any]],
    beta: float | None,
    risk_profile: str | None,
) -> list[dict[str, str]]:
    obs: list[dict[str, str]] = []

    if concentration["flag"] == "high":
        obs.append({
            "severity": "warning",
            "text": (
                f"{concentration['top_position_pct']}% of risk sits in {concentration['top_holding']} — "
                f"this position dominates every stress scenario."
            ),
        })
    elif concentration["flag"] == "warning":
        obs.append({
            "severity": "info",
            "text": (
                f"{concentration['top_position_pct']}% in {concentration['top_holding']} is a meaningful "
                "single-name exposure to watch in a downturn."
            ),
        })

    if beta is not None:
        if beta >= 1.15:
            obs.append({
                "severity": "warning",
                "text": (
                    f"Portfolio beta proxy ~{beta:.2f}: the book moves roughly "
                    f"{int(round((beta - 1.0) * 100))}% more than the broad market in a drawdown."
                ),
            })
        elif beta <= 0.75:
            obs.append({
                "severity": "info",
                "text": (
                    f"Portfolio beta proxy ~{beta:.2f}: this book typically rides through drawdowns "
                    "lighter than the broad market."
                ),
            })

    if scenarios:
        worst = min(scenarios, key=lambda s: s["portfolio_estimated_drop_pct"])
        obs.append({
            "severity": "info",
            "text": (
                f"Worst-case scenario shown: a {abs(worst['market_shock_pct'])}% market drop "
                f"maps to roughly {worst['portfolio_estimated_drop_pct']}% on your portfolio."
            ),
        })

    if currency["flag"] in ("moderate", "high"):
        obs.append({
            "severity": "info",
            "text": (
                f"{currency['non_base_pct']}% of your book is in non-{currency['base_currency_assumed']} "
                "currencies — FX moves can add or subtract several percent on top of equity moves."
            ),
        })

    if risk_profile == "conservative" and beta is not None and beta >= 1.10:
        obs.append({
            "severity": "warning",
            "text": (
                "Your stated risk profile is conservative but the portfolio beta is above the broad "
                "market. A defensive tilt (bonds, dividend payers, lower-beta sectors) would line up better."
            ),
        })

    if not obs:
        obs.append({
            "severity": "info",
            "text": "Nothing flagged. Risk concentration and scenario sensitivity look reasonable for the book.",
        })
    return obs


def _empty_response() -> dict[str, Any]:
    return {
        "agent": "risk_assessment",
        "mode": "build",
        "summary": (
            "You dont have any positions, so theres nothing to stress-test yet. "
            "Once you add positions, this agent can show concentration risk, a "
            "beta-style sensitivity read, currency exposure, and a scenario drawdown."
        ),
        "concentration_risk": {
            "top_position_pct": 0.0, "top_3_positions_pct": 0.0, "flag": "n/a", "top_holding": None,
        },
        "currency_exposure": {"breakdown": {}, "non_base_pct": 0.0, "flag": "n/a"},
        "scenarios": [],
        "top_risk_contributors": [],
        "portfolio_beta_proxy": None,
        "observations": [{"severity": "info", "text": "Empty portfolio — add positions to run a stress test."}],
        "disclaimer": DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def assess_risk(user_context: dict[str, Any], *, query: str) -> dict[str, Any]:
    positions = user_context.get("positions") or []
    if not positions:
        return _empty_response()

    rows, summary = _portfolio_rows(positions)
    if not rows:
        return _empty_response()

    shocks = _parse_market_shocks(query) or _default_shocks()
    concentration = _concentration_block(rows)
    currency = _currency_exposure(rows)
    scenarios = _scenarios(rows, shocks)
    beta = _portfolio_weighted_beta(rows)
    contributors = _drawdown_contributors(rows)
    obs = _observations(
        rows,
        concentration=concentration,
        currency=currency,
        scenarios=scenarios,
        beta=beta,
        risk_profile=user_context.get("risk_profile"),
    )

    return {
        "agent": "risk_assessment",
        "mode": "monitor",
        "summary_stats": summary,
        "concentration_risk": concentration,
        "currency_exposure": currency,
        "scenarios_used": shocks,
        "scenarios": scenarios,
        "top_risk_contributors": contributors,
        "portfolio_beta_proxy": _round(beta, 3),
        "observations": obs,
        "disclaimer": DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Streaming agent
# ---------------------------------------------------------------------------


NARRATIVE_SYSTEM = """\
You are Icetea's risk analyst speaking to a novice investor. Write 3 to 5
short sentences. Open with the single biggest risk in the book (concentration
or beta tilt), name the actual stress numbers from the structured payload
(do not invent new numbers), and close with one practical, conservative next
step. No financial advice language; this is educational. Do NOT repeat the
disclaimer.

""" + MODEL_INJECTION_GUARD


def _build_narrative_user_msg(query: str, structured: dict[str, Any]) -> str:
    return (
        f"USER QUERY: {query}\n\n"
        f"STRUCTURED RISK ASSESSMENT (use these numbers, dont invent new ones):\n{structured}\n"
    )


def _deterministic_intro(structured: dict[str, Any]) -> str:
    if structured.get("mode") == "build":
        return structured.get("summary", "")
    conc = structured.get("concentration_risk") or {}
    scenarios = structured.get("scenarios") or []
    beta = structured.get("portfolio_beta_proxy")
    parts: list[str] = []
    if conc.get("flag") in ("high", "warning"):
        parts.append(
            f"Largest single risk: {conc.get('top_holding')} at {conc.get('top_position_pct')}% of the book. "
        )
    if beta is not None:
        parts.append(f"Portfolio beta proxy is around {beta:.2f}. ")
    if scenarios:
        worst = min(scenarios, key=lambda s: s.get("portfolio_estimated_drop_pct", 0))
        parts.append(
            f"In a {abs(worst['market_shock_pct'])}% market drop the portfolio is modelled to fall "
            f"about {worst['portfolio_estimated_drop_pct']}%."
        )
    if not parts:
        parts.append("Risk profile looks contained — see the structured payload for the numbers.")
    return "".join(parts).strip()


def _format_plain(structured: dict[str, Any]) -> str:
    if structured.get("mode") == "build":
        return structured.get("summary", "")
    out: list[str] = ["RISK ASSESSMENT", ""]
    conc = structured.get("concentration_risk") or {}
    out.append(
        f"Concentration: {conc.get('flag')} — top position {conc.get('top_holding')} at "
        f"{conc.get('top_position_pct')}% (top 3 at {conc.get('top_3_positions_pct')}%)."
    )
    beta = structured.get("portfolio_beta_proxy")
    if beta is not None:
        out.append(f"Portfolio beta proxy: {beta}")
    cur = structured.get("currency_exposure") or {}
    if cur.get("breakdown"):
        out.append(
            f"Currency exposure ({cur.get('flag')}): " + ", ".join(
                f"{k} {v}%" for k, v in cur["breakdown"].items()
            )
        )
    out.append("")
    out.append("Stress scenarios:")
    for s in structured.get("scenarios") or []:
        out.append(
            f"  • Market {s['market_shock_pct']}% → portfolio {s['portfolio_estimated_drop_pct']}% "
            f"(beta-proxy {s['beta_proxy_used']})"
            + (f", est loss ~{s['estimated_loss_amount']}" if s.get("estimated_loss_amount") is not None else "")
        )
    out.append("")
    out.append("Top risk contributors:")
    for c in structured.get("top_risk_contributors") or []:
        out.append(
            f"  • {c['ticker']} — weight {c['weight_pct']}%, beta-proxy {c['beta_proxy']}, "
            f"contributes ~{c['share_of_portfolio_beta']}% of portfolio beta"
        )
    out.append("")
    out.append("Observations:")
    for o in structured.get("observations") or []:
        out.append(f"  [{str(o.get('severity', 'info')).upper()}] {o.get('text', '').strip()}")
    out.append("")
    out.append("Disclaimer:")
    out.append(f"  {structured.get('disclaimer', '').strip()}")
    return "\n".join(out)


def _split_for_stream(text: str, *, chunk_size: int = 32) -> list[str]:
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


class RiskAssessmentAgent:
    name = "risk_assessment"

    async def run(
        self,
        *,
        query: str,
        user_context: dict[str, Any],
        classification: dict[str, Any],
        llm: LLMClient | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        try:
            structured = assess_risk(user_context, query=query)
        except Exception as exc:
            logger.exception("Risk Assessment computation failed")
            yield {"type": "data", "delta": "I couldnt run the stress numbers just now. "}
            yield {
                "type": "structured",
                "payload": {
                    "agent": self.name,
                    "error": "compute_failed",
                    "message": str(exc),
                    "disclaimer": DISCLAIMER,
                },
            }
            return

        client = llm if (llm is not None and hasattr(llm, "stream_text")) else _maybe_default_llm()
        if client is not None and not hasattr(client, "stream_text"):
            client = None

        if client is None:
            intro = _deterministic_intro(structured)
            for chunk in _split_for_stream(intro):
                yield {"type": "data", "delta": chunk}
            payload = dict(structured)
            payload["message"] = _format_plain(structured)
            yield {"type": "structured", "payload": payload}
            return

        hist = list(conversation_history or [])
        if hist and hist[-1].get("role") == "user":
            hist = hist[:-1]
        messages = assemble_messages(
            system=NARRATIVE_SYSTEM,
            history=hist,
            user=_build_narrative_user_msg(query, structured),
        )
        try:
            async for piece in client.stream_text(messages, temperature=0.2, max_tokens=320):
                yield {"type": "data", "delta": piece}
        except LLMError as exc:
            logger.warning("Risk Assessment LLM narrative failed: %s", exc)
            intro = _deterministic_intro(structured)
            for chunk in _split_for_stream(intro):
                yield {"type": "data", "delta": chunk}

        payload = dict(structured)
        payload["message"] = _format_plain(structured)
        yield {"type": "structured", "payload": payload}


def _maybe_default_llm() -> LLMClient | None:
    try:
        return get_llm_client()
    except Exception:
        return None
