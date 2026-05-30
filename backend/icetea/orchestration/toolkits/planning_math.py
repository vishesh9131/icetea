"""
Retirement / long-horizon planning math.

All deterministic financial formulas — no Monte Carlo here, no regulated suitability.
The point is to STOP the planner from looping on "need more info" by giving it a way
to bracket scenarios from whatever inputs it does have (age / income / horizon / risk
profile / existing savings). Anything missing is filled by named assumptions that
get echoed back so the user can see them.

Formulas used:

- Future value of a series (ordinary annuity, end-of-period):
      FV = PMT * ((1 + r)^n - 1) / r            (r != 0)
      FV = PMT * n                              (r == 0)
- Future value of a lump sum:
      FV = P * (1 + r)^n
- Required corpus from annual income at a withdrawal rate:
      Corpus = AnnualIncome / WithdrawalRate
- Back-solving monthly contribution from a target FV and starting balance:
      PMT = (FV_target - P*(1+r)^n) * r / ((1+r)^n - 1)
- Inflation adjustment / real return:
      real = (1 + nominal) / (1 + inflation) - 1
"""
from __future__ import annotations

import math
import re
from typing import Any


# Industry-convention assumption knobs (NOT tuned to any specific test case).
# Names + values are passed back in the response so the user / advisor can see them.
_DEFAULT_WITHDRAWAL_RATES = (0.03, 0.035, 0.04)  # 3% / 3.5% / 4% (conservative -> classic SWR)
_DEFAULT_REPLACEMENT_RATIO_RANGE = (0.60, 0.80)  # 60–80% income replacement target band
_DEFAULT_INFLATION = 0.025                       # 2.5% long-term

# Real returns (nominal minus inflation) by stated risk profile — used only as labelled scenarios.
_REAL_RETURNS_BY_RISK: dict[str, tuple[float, float, float]] = {
    "conservative": (0.015, 0.030, 0.045),
    "moderate":     (0.030, 0.050, 0.065),
    "aggressive":   (0.040, 0.065, 0.080),
}
_DEFAULT_REAL_RETURNS = _REAL_RETURNS_BY_RISK["moderate"]

# Sequence-of-returns / recession haircut to apply on top of the base corpus need.
# (A blunt deterministic stand-in for "low-return decade right before retirement".)
_SEQUENCE_RISK_HAIRCUT = 0.15  # corpus need expands by ~15% under bad-sequence stress


def infer_reference_pre_retirement_income_band(age: int | None) -> tuple[float, float]:
    """Broad plausible gross-income bracket when the user gave no salary.

    Same spirit as a human planner sketching "typical full-time household earnings"
    before attaching replacement ratios. Not personalised — always labelled in output.

    Age only shifts which decade-shaped bracket we use; numbers are round anchors,
    not calibrated to any external dataset per request.
    """
    if age is None:
        return (48_000.0, 92_000.0)
    if age < 25:
        return (36_000.0, 62_000.0)
    if age < 35:
        return (45_000.0, 95_000.0)
    if age < 45:
        return (52_000.0, 115_000.0)
    if age < 55:
        return (48_000.0, 105_000.0)
    return (40_000.0, 85_000.0)


# ---------- input sniffing ----------

def _coerce_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def _coerce_int(x: Any) -> int | None:
    v = _coerce_float(x)
    return int(v) if v is not None else None


def _parse_horizon_from_query(query: str) -> int | None:
    if not query:
        return None
    m = re.search(r"(\d+)\s*(?:years?|yrs?)\b", query.lower())
    return int(m.group(1)) if m else None


def _parse_monthly_income_target(query: str) -> float | None:
    """Best-effort extraction of '$Xk monthly' / '$X/month' style targets from free text."""
    if not query:
        return None
    q = query.lower()
    pat = re.compile(
        r"\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(k|thousand|m|million)?\s*(?:/|per)?\s*"
        r"(?:a\s+)?(month|mo|monthly)",
        re.IGNORECASE,
    )
    m = pat.search(q)
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    try:
        v = float(raw)
    except ValueError:
        return None
    unit = (m.group(2) or "").lower()
    if unit in {"k", "thousand"}:
        v *= 1_000
    elif unit in {"m", "million"}:
        v *= 1_000_000
    return v


def detect_planning_signals(query: str, user_context: dict[str, Any]) -> dict[str, Any]:
    """Lightweight planner pre-pass: pull what we can from query + user_context."""
    q = (query or "").strip()
    ql = q.lower()
    age = _coerce_int(user_context.get("age"))
    annual_income = _coerce_float(user_context.get("annual_income"))
    if annual_income is None:
        annual_income = _coerce_float((user_context.get("preferences") or {}).get("annual_income"))
    current_savings = _coerce_float(user_context.get("current_savings"))
    monthly_contribution = _coerce_float(user_context.get("monthly_contribution"))

    horizon_years = _parse_horizon_from_query(q)
    if horizon_years is None:
        horizon_years = _coerce_int(user_context.get("horizon_years"))

    risk_profile = str(user_context.get("risk_profile") or "").strip().lower() or None
    base_currency = str(user_context.get("base_currency") or "USD").strip().upper()

    monthly_income_target = _parse_monthly_income_target(q)
    explicit_target = _coerce_float((user_context.get("preferences") or {}).get("monthly_income_target"))
    if monthly_income_target is None and explicit_target is not None:
        monthly_income_target = explicit_target

    is_retirement = any(t in ql for t in ("retire", "retirement", "fire ", " fire", "early retire"))
    is_passive_income = "passive income" in ql or "monthly income" in ql or "dividend" in ql
    is_multi_step = any(t in ql for t in ("plan", "roadmap", "milestone", "phase", "decade"))

    return {
        "age": age,
        "annual_income": annual_income,
        "current_savings": current_savings,
        "monthly_contribution_known": monthly_contribution,
        "horizon_years": horizon_years,
        "risk_profile": risk_profile,
        "base_currency": base_currency,
        "monthly_income_target_parsed": monthly_income_target,
        "is_retirement_question": is_retirement,
        "is_passive_income_question": is_passive_income,
        "is_multi_step_plan": is_multi_step or is_retirement,
    }


# ---------- core finance formulas ----------

def future_value_annuity(pmt: float, monthly_rate: float, months: int) -> float:
    if months <= 0:
        return 0.0
    if monthly_rate == 0:
        return float(pmt) * months
    return float(pmt) * ((1.0 + monthly_rate) ** months - 1.0) / monthly_rate


def future_value_lump(principal: float, monthly_rate: float, months: int) -> float:
    if months <= 0 or principal <= 0:
        return float(principal or 0.0)
    return float(principal) * ((1.0 + monthly_rate) ** months)


def required_contribution_monthly(
    target_fv: float,
    starting_balance: float,
    monthly_rate: float,
    months: int,
) -> float | None:
    """PMT that, on top of starting_balance compounding, reaches target_fv."""
    if months <= 0:
        return None
    gap = float(target_fv) - future_value_lump(starting_balance, monthly_rate, months)
    if gap <= 0:
        return 0.0  # already on track
    if monthly_rate == 0:
        return gap / months
    factor = ((1.0 + monthly_rate) ** months - 1.0) / monthly_rate
    if factor <= 0:
        return None
    return gap / factor


def annual_to_monthly_rate(annual_rate: float) -> float:
    return (1.0 + float(annual_rate)) ** (1.0 / 12.0) - 1.0


def real_return(nominal: float, inflation: float = _DEFAULT_INFLATION) -> float:
    return (1.0 + float(nominal)) / (1.0 + float(inflation)) - 1.0


# ---------- bundles the planner / projection agents use ----------

def estimate_income_target_band(
    *,
    annual_income: float | None,
    monthly_target_parsed: float | None,
    age: int | None = None,
    replacement_ratio_range: tuple[float, float] = _DEFAULT_REPLACEMENT_RATIO_RANGE,
) -> dict[str, Any]:
    """Retirement spending need band (today's currency): stated targets, or replacement × income / reference."""
    if monthly_target_parsed is not None and monthly_target_parsed > 0:
        annual = float(monthly_target_parsed) * 12.0
        return {
            "source": "user_stated_monthly_target",
            "annual_low": round(annual, 2),
            "annual_high": round(annual, 2),
            "monthly_low": round(annual / 12.0, 2),
            "monthly_high": round(annual / 12.0, 2),
            "replacement_ratio_used": None,
            "reference_pre_retirement_income_band": None,
        }
    if annual_income is None or annual_income <= 0:
        ref_lo, ref_hi = infer_reference_pre_retirement_income_band(age)
        lo_r, hi_r = replacement_ratio_range
        # Retirement spending corners: low replacement × low ref .. high replacement × high ref
        spend_lo = float(ref_lo) * float(lo_r)
        spend_hi = float(ref_hi) * float(hi_r)
        return {
            "source": "assumed_reference_pre_retirement_income_then_replacement",
            "annual_low": round(spend_lo, 2),
            "annual_high": round(spend_hi, 2),
            "monthly_low": round(spend_lo / 12.0, 2),
            "monthly_high": round(spend_hi / 12.0, 2),
            "replacement_ratio_used": [lo_r, hi_r],
            "reference_pre_retirement_income_band": [ref_lo, ref_hi],
            "reference_age_used_for_band": age,
            "note": (
                "No salary on file — used age-tier reference gross-income bracket × replacement ratios "
                "to bracket retirement spending need (labelled, revise when you share actual income)."
            ),
        }
    lo, hi = replacement_ratio_range
    a_lo = float(annual_income) * float(lo)
    a_hi = float(annual_income) * float(hi)
    return {
        "source": "assumed_income_replacement",
        "annual_low": round(a_lo, 2),
        "annual_high": round(a_hi, 2),
        "monthly_low": round(a_lo / 12.0, 2),
        "monthly_high": round(a_hi / 12.0, 2),
        "replacement_ratio_used": [lo, hi],
        "reference_pre_retirement_income_band": None,
    }


def required_corpus_band(
    annual_target_low: float | None,
    annual_target_high: float | None,
    *,
    withdrawal_rates: tuple[float, ...] = _DEFAULT_WITHDRAWAL_RATES,
    sequence_haircut: float = _SEQUENCE_RISK_HAIRCUT,
) -> dict[str, Any]:
    """Brackets corpus need across withdrawal rates + a sequence-of-returns stress."""
    if annual_target_low is None or annual_target_high is None:
        return {
            "corpus_per_wr": [],
            "corpus_band_low": None,
            "corpus_band_high": None,
            "withdrawal_rates_used": list(withdrawal_rates),
            "sequence_stress_haircut": sequence_haircut,
        }
    rows: list[dict[str, Any]] = []
    spans: list[float] = []
    for wr in withdrawal_rates:
        lo = float(annual_target_low) / float(wr)
        hi = float(annual_target_high) / float(wr)
        rows.append(
            {
                "withdrawal_rate": wr,
                "corpus_low": round(lo, 2),
                "corpus_high": round(hi, 2),
            }
        )
        spans.extend([lo, hi])
    base_low, base_high = (min(spans), max(spans)) if spans else (None, None)
    stressed_low = base_low * (1.0 + sequence_haircut) if base_low is not None else None
    stressed_high = base_high * (1.0 + sequence_haircut) if base_high is not None else None
    return {
        "corpus_per_wr": rows,
        "corpus_band_low": round(base_low, 2) if base_low is not None else None,
        "corpus_band_high": round(base_high, 2) if base_high is not None else None,
        "corpus_band_low_sequence_stressed": round(stressed_low, 2) if stressed_low is not None else None,
        "corpus_band_high_sequence_stressed": round(stressed_high, 2) if stressed_high is not None else None,
        "withdrawal_rates_used": list(withdrawal_rates),
        "sequence_stress_haircut": sequence_haircut,
    }


def contribution_scenarios(
    *,
    corpus_low: float | None,
    corpus_high: float | None,
    horizon_years: int | None,
    starting_balance: float | None,
    real_returns: tuple[float, float, float] = _DEFAULT_REAL_RETURNS,
) -> dict[str, Any]:
    """Solve monthly contribution at conservative / base / optimistic real returns."""
    if corpus_low is None or corpus_high is None or horizon_years is None or horizon_years <= 0:
        return {
            "scenarios": [],
            "real_returns_used": list(real_returns),
            "starting_balance_used": starting_balance or 0.0,
            "horizon_years": horizon_years,
        }
    months = int(horizon_years) * 12
    sb = float(starting_balance or 0.0)
    rows: list[dict[str, Any]] = []
    labels = ("conservative", "base", "optimistic")
    for label, rr in zip(labels, real_returns):
        mr = annual_to_monthly_rate(rr)
        pmt_lo = required_contribution_monthly(corpus_low, sb, mr, months)
        pmt_hi = required_contribution_monthly(corpus_high, sb, mr, months)
        rows.append(
            {
                "scenario": label,
                "real_annual_return": rr,
                "monthly_contribution_low": None if pmt_lo is None else round(pmt_lo, 2),
                "monthly_contribution_high": None if pmt_hi is None else round(pmt_hi, 2),
            }
        )
    return {
        "scenarios": rows,
        "real_returns_used": list(real_returns),
        "starting_balance_used": sb,
        "horizon_years": int(horizon_years),
    }


def stress_test_scenarios(
    *,
    corpus_band_low: float | None,
    corpus_band_high: float | None,
    horizon_years: int | None,
    starting_balance: float | None,
    base_real_returns: tuple[float, float, float] = _DEFAULT_REAL_RETURNS,
) -> dict[str, Any]:
    """Deterministic worst-case sleeves (low-return decade, recession year 1).

    Not Monte Carlo — explicitly labelled deterministic. We perturb the real
    return path and compare required contribution at each path.
    """
    if corpus_band_low is None or corpus_band_high is None or not horizon_years:
        return {"paths": []}
    months = int(horizon_years) * 12
    sb = float(starting_balance or 0.0)
    paths: list[dict[str, Any]] = []

    def _pmt_at(rr: float) -> tuple[float | None, float | None]:
        mr = annual_to_monthly_rate(rr)
        return (
            required_contribution_monthly(corpus_band_low, sb, mr, months),
            required_contribution_monthly(corpus_band_high, sb, mr, months),
        )

    conservative_rr, base_rr, optimistic_rr = base_real_returns
    # Path A: lost decade (return clipped to ~half conservative for full horizon)
    rr_A = max(0.0, conservative_rr * 0.5)
    pmt_A_lo, pmt_A_hi = _pmt_at(rr_A)
    paths.append(
        {
            "name": "lost_decade",
            "real_annual_return_used": rr_A,
            "monthly_contribution_low": None if pmt_A_lo is None else round(pmt_A_lo, 2),
            "monthly_contribution_high": None if pmt_A_hi is None else round(pmt_A_hi, 2),
        }
    )
    # Path B: bad early sequence (use conservative for whole horizon as proxy)
    pmt_B_lo, pmt_B_hi = _pmt_at(conservative_rr)
    paths.append(
        {
            "name": "bad_early_sequence_proxy",
            "real_annual_return_used": conservative_rr,
            "monthly_contribution_low": None if pmt_B_lo is None else round(pmt_B_lo, 2),
            "monthly_contribution_high": None if pmt_B_hi is None else round(pmt_B_hi, 2),
        }
    )
    # Path C: tailwind (optimistic)
    pmt_C_lo, pmt_C_hi = _pmt_at(optimistic_rr)
    paths.append(
        {
            "name": "tailwind",
            "real_annual_return_used": optimistic_rr,
            "monthly_contribution_low": None if pmt_C_lo is None else round(pmt_C_lo, 2),
            "monthly_contribution_high": None if pmt_C_hi is None else round(pmt_C_hi, 2),
        }
    )
    return {"paths": paths}


def build_retirement_bundle(
    *,
    query: str,
    user_context: dict[str, Any],
) -> dict[str, Any]:
    """One-shot deterministic bundle used by the planner panel + single-agent fallback.

    Labels every assumption. Missing salary triggers a reference gross-income bracket by age tier,
    then replacement ratios — corpus still brackets unless horizon is unknown (contributions need years).
    """
    sig = detect_planning_signals(query, user_context)
    risk = sig.get("risk_profile")
    real_returns = _REAL_RETURNS_BY_RISK.get(str(risk or "").lower(), _DEFAULT_REAL_RETURNS)

    income_band = estimate_income_target_band(
        annual_income=sig.get("annual_income"),
        monthly_target_parsed=sig.get("monthly_income_target_parsed"),
        age=sig.get("age"),
    )
    corpus = required_corpus_band(
        income_band.get("annual_low"),
        income_band.get("annual_high"),
    )
    contrib = contribution_scenarios(
        corpus_low=corpus.get("corpus_band_low"),
        corpus_high=corpus.get("corpus_band_high"),
        horizon_years=sig.get("horizon_years"),
        starting_balance=sig.get("current_savings"),
        real_returns=real_returns,
    )
    stress = stress_test_scenarios(
        corpus_band_low=corpus.get("corpus_band_low"),
        corpus_band_high=corpus.get("corpus_band_high"),
        horizon_years=sig.get("horizon_years"),
        starting_balance=sig.get("current_savings"),
        base_real_returns=real_returns,
    )

    missing: list[str] = []
    if sig.get("current_savings") is None:
        missing.append("current_savings_optional_for_back_solve")
    if sig.get("horizon_years") is None:
        missing.append("horizon_years")
    if sig.get("annual_income") is None and sig.get("monthly_income_target_parsed") is None:
        missing.append("stated_annual_or_monthly_income_optional_refinement")

    return {
        "inputs_detected": sig,
        "assumptions": {
            "replacement_ratio_range": _DEFAULT_REPLACEMENT_RATIO_RANGE,
            "withdrawal_rates": _DEFAULT_WITHDRAWAL_RATES,
            "inflation_long_term": _DEFAULT_INFLATION,
            "real_returns_by_scenario": {
                "conservative": real_returns[0],
                "base": real_returns[1],
                "optimistic": real_returns[2],
            },
            "sequence_stress_haircut": _SEQUENCE_RISK_HAIRCUT,
            "risk_profile_used_for_returns": risk or "moderate (default)",
        },
        "income_target_band": income_band,
        "required_corpus": corpus,
        "contribution_solver": contrib,
        "stress_tests": stress,
        "missing_inputs_for_higher_fidelity": missing,
        "math_disclaimer": (
            "Deterministic textbook formulas only (FV annuity, withdrawal-rate corpus, real-return scenarios). "
            "Not a Monte Carlo, not regulated suitability. Assumptions are labelled — a certified planner should "
            "tighten them with your actual tax accounts, contribution caps, and cash-flow detail."
        ),
    }


# ---------- presentation helpers ----------

def _fmt_money(x: float | None, currency: str = "USD") -> str:
    if x is None:
        return "n/a"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "n/a"
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1_000_000:
        return f"{sign}{currency} {v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"{sign}{currency} {v/1_000:.1f}k"
    return f"{sign}{currency} {v:,.0f}"


def render_planner_summary(bundle: dict[str, Any], *, currency: str = "USD") -> str:
    """Plain-prose summary an agent can drop into its utterance."""
    sig = bundle.get("inputs_detected") or {}
    assumptions = bundle.get("assumptions") or {}
    ib = bundle.get("income_target_band") or {}
    cb = bundle.get("required_corpus") or {}
    cs = bundle.get("contribution_solver") or {}
    stress = bundle.get("stress_tests") or {}

    horizon = sig.get("horizon_years")
    age = sig.get("age")
    inc = sig.get("annual_income")
    risk = assumptions.get("risk_profile_used_for_returns")

    lines: list[str] = []
    head_bits = []
    if age is not None:
        head_bits.append(f"age {age}")
    if horizon:
        head_bits.append(f"~{horizon}y horizon")
    if inc is not None:
        head_bits.append(f"stated income {_fmt_money(inc, currency)}")
    if risk:
        head_bits.append(f"risk: {risk}")
    if head_bits:
        lines.append("Inputs the math used: " + ", ".join(head_bits) + ".")

    if ib.get("annual_low") is not None:
        extra = ""
        ref = ib.get("reference_pre_retirement_income_band")
        if isinstance(ref, list) and len(ref) == 2:
            extra = (
                f" Reference gross-income bracket assumed pre-retirement: "
                f"{_fmt_money(ref[0], currency)}–{_fmt_money(ref[1], currency)}/yr "
                f"(age tier). "
            )
        lines.append(
            f"Income target band (today's {currency}, retirement spending): "
            f"{_fmt_money(ib['annual_low'], currency)}–{_fmt_money(ib['annual_high'], currency)} per year "
            f"({_fmt_money(ib.get('monthly_low'), currency)}–{_fmt_money(ib.get('monthly_high'), currency)} per month). "
            f"Source: {ib.get('source')}.{extra}"
        )
    else:
        lines.append("Income target band unavailable — add horizon or query text so spending can be bracketed.")

    if cb.get("corpus_band_low") is not None:
        lines.append(
            f"Required corpus across withdrawal rates "
            f"({', '.join(f'{int(r*1000)/10}%' for r in cb.get('withdrawal_rates_used') or [])}): "
            f"{_fmt_money(cb['corpus_band_low'], currency)}–{_fmt_money(cb['corpus_band_high'], currency)}. "
            f"Sequence-stressed: {_fmt_money(cb.get('corpus_band_low_sequence_stressed'), currency)}–"
            f"{_fmt_money(cb.get('corpus_band_high_sequence_stressed'), currency)}."
        )

    scs = cs.get("scenarios") or []
    if scs:
        chunks = []
        for r in scs:
            lo = r.get("monthly_contribution_low")
            hi = r.get("monthly_contribution_high")
            chunks.append(
                f"{r.get('scenario')} (real {r.get('real_annual_return'):.1%}): "
                f"{_fmt_money(lo, currency)}–{_fmt_money(hi, currency)}/mo"
            )
        lines.append("Monthly contribution to reach the corpus band — " + "; ".join(chunks) + ".")

    paths = stress.get("paths") or []
    if paths:
        lost = next((p for p in paths if p.get("name") == "lost_decade"), None)
        if lost and lost.get("monthly_contribution_low") is not None:
            lines.append(
                "Lost-decade stress (returns clipped roughly in half): "
                f"contribution band widens to {_fmt_money(lost['monthly_contribution_low'], currency)}"
                f"–{_fmt_money(lost['monthly_contribution_high'], currency)}/mo."
            )

    missing = bundle.get("missing_inputs_for_higher_fidelity") or []
    if missing:
        lines.append("Highest-value missing input: " + missing[0].replace("_", " ") + ".")

    lines.append(bundle.get("math_disclaimer") or "")
    return "\n".join(s for s in lines if s).strip()
