"""
Intent classifier.

One LLM call per query, period. The LLM must return a single JSON object
holding intent, the agent we should route to, every entity it can extract,
and an *informational* safety verdict (the real safety guard already ran
before we got here).

Failure mode: if the LLM raises, returns invalid JSON, or returns an unknown
agent, we fall back to `general_query` with empty entities. The pipeline
keeps moving — the request never crashes on a classifier failure.

Follow-up resolution is done in the prompt: we feed the prior user turns
plus the last-known carryover (last ticker(s), last intent) so phrases like
"how much do i own?" or "what about AMD?" resolve to the right entities and
the right agent.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .llm import LLMClient, LLMError, assemble_messages, get_llm_client
from .session import SessionState


logger = logging.getLogger(__name__)


# Canonical agent taxonomy. Match the one used in
# fixtures/test_queries/intent_classification.json. Anything else from the
# LLM is dropped to `general_query`.
AGENT_TAXONOMY: tuple[str, ...] = (
    "portfolio_health",
    "market_research",
    "investment_strategy",
    "financial_planning",
    "financial_calculator",
    "risk_assessment",
    "product_recommendation",
    "predictive_analysis",
    "customer_support",
    "general_query",
    # The follow-up fixture also uses "portfolio_query" for "how much do i own?".
    # We accept it as a valid agent so test cases can route to a portfolio
    # lookup even if we don't ship that specialist in this build (it goes
    # through the stub registry).
    "portfolio_query",
)


@dataclass
class Classification:
    agent: str
    intent: str
    entities: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    safety_verdict: dict[str, Any] = field(default_factory=lambda: {"category": None, "rationale": ""})
    raw: dict[str, Any] = field(default_factory=dict)
    fallback_used: bool = False
    error: str | None = None


# Stable JSON schema. We hand it to OpenAI's structured-output endpoint when
# we can; for VLLM we just shove it into the prompt and rely on json mode.
CLASSIFIER_SCHEMA: dict[str, Any] = {
    "title": "intent_classification",
    "type": "object",
    "additionalProperties": False,
    "required": ["agent", "intent", "entities", "confidence", "safety_verdict"],
    "properties": {
        "agent": {"type": "string", "enum": list(AGENT_TAXONOMY)},
        "intent": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "entities": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "tickers": {"type": "array", "items": {"type": "string"}},
                "topics": {"type": "array", "items": {"type": "string"}},
                "sectors": {"type": "array", "items": {"type": "string"}},
                "amount": {"type": "number"},
                "currency": {"type": "string"},
                "rate": {"type": "number"},
                "period_years": {"type": "integer"},
                "frequency": {"type": "string"},
                "horizon": {"type": "string"},
                "time_period": {"type": "string"},
                "index": {"type": "string"},
                "action": {"type": "string"},
                "goal": {"type": "string"},
            },
        },
        "safety_verdict": {
            "type": "object",
            "additionalProperties": False,
            "required": ["category", "rationale"],
            "properties": {
                "category": {"type": ["string", "null"]},
                "rationale": {"type": "string"},
            },
        },
    },
}


SYSTEM_PROMPT = """\
You are the intent router for Valura, a wealth-management AI for novice investors.
Your job: classify ONE user turn into a single agent and extract every entity you can.

Agents (pick exactly one):
- portfolio_health      : how is my portfolio doing, diversified?, am i beating the market, concentration, health check, review my holdings
- portfolio_query       : factual lookup about the user's own holdings ("how much do i own", "show my AAPL position")
- market_research       : factual / recent info about an instrument, sector, index, or market event
- investment_strategy   : should i buy/sell/rebalance/hedge, allocation guidance
- financial_planning    : long-term planning, retirement, FIRE, education, house, savings goal
- financial_calculator  : deterministic numeric computation (DCA returns, mortgage, FX, future value, tax)
- risk_assessment       : beta, drawdown, stress test, currency exposure, scenario analysis
- product_recommendation: recommend specific funds / ETFs / products
- predictive_analysis   : forecast, "where will X be in N", trend extrapolation
- customer_support      : platform issues, account questions, how-to-use-app
- general_query         : greeting, thanks, definition, educational, gibberish

Entity vocabulary (use ONLY these field names, omit fields you cannot fill):
- tickers       : array of uppercase symbols, with exchange suffix where natural (AAPL, ASML.AS, 7203.T, HSBA.L)
- topics        : array of lowercase / canonical topic strings (mutual fund, ETF, beta, FX, DCA)
- sectors       : array (technology, healthcare, financials)
- amount        : number, in the unit of `currency` if present
- currency      : ISO 4217 (USD, EUR, GBP, JPY)
- rate          : decimal (0.08 for 8%)
- period_years  : integer
- frequency     : daily | weekly | monthly | yearly
- horizon       : 6_months | 1_year | 5_years
- time_period   : today | this_week | this_month | this_year
- index         : exact canonical (S&P 500, FTSE 100, NIKKEI 225, MSCI World)
- action        : buy | sell | hold | hedge | rebalance
- goal          : retirement | education | house | FIRE | emergency_fund

Rules:
1. Resolve follow-ups using the prior user turns: pronouns, "what about X?", "compare them", "should I sell some?".
2. A bare ticker with no verb -> market_research with that ticker.
3. Greetings ("hi", "thanks") -> general_query, empty entities.
4. Gibberish -> general_query, empty entities, low confidence.
5. Multi-intent: pick the PRIMARY intent. ("how is my portfolio doing and what should i sell?" -> portfolio_health, action=sell.)
6. NEVER invent tickers. Only emit a ticker you can read from the user's words OR carry over from the prior turn.
7. Output ONE JSON object that matches the provided schema. No commentary.

The `safety_verdict` field is informational only. Set `category` to null if nothing concerning;
otherwise use one of: insider_trading, market_manipulation, money_laundering, guaranteed_returns,
reckless_advice, sanctions_evasion, fraud.
"""


def _build_user_message(
    *,
    query: str,
    prior_user_turns: Iterable[str],
    user_context: dict[str, Any] | None,
    carryover: dict[str, Any] | None,
) -> str:
    parts = [f"CURRENT_TURN: {query.strip()}"]
    prior = list(prior_user_turns)
    if prior:
        joined = "\n".join(f"- {t}" for t in prior[-6:])
        parts.append(f"PRIOR_USER_TURNS:\n{joined}")
    if carryover:
        parts.append(f"CARRYOVER: {json.dumps(carryover, ensure_ascii=False)}")
    if user_context:
        # Keep this small — full portfolio in here would burn tokens.
        slim = {
            "user_id": user_context.get("user_id"),
            "country": user_context.get("country"),
            "base_currency": user_context.get("base_currency"),
            "risk_profile": user_context.get("risk_profile"),
            "has_positions": bool(user_context.get("positions")),
        }
        parts.append(f"USER_CONTEXT: {json.dumps(slim, ensure_ascii=False)}")
    parts.append('Respond with one JSON object matching the schema. Do not wrap it in markdown.')
    return "\n\n".join(parts)


def _coerce(payload: dict[str, Any]) -> Classification:
    agent = str(payload.get("agent", "")).strip().lower()
    if agent not in AGENT_TAXONOMY:
        # try aliases the LLM might emit
        aliases = {
            "portfolio": "portfolio_health",
            "research": "market_research",
            "support": "customer_support",
            "general": "general_query",
        }
        agent = aliases.get(agent, "general_query")

    entities = payload.get("entities") or {}
    if not isinstance(entities, dict):
        entities = {}

    tickers = entities.get("tickers")
    if isinstance(tickers, list):
        entities["tickers"] = [str(t).upper() for t in tickers if str(t).strip()]

    safety = payload.get("safety_verdict") or {"category": None, "rationale": ""}
    if not isinstance(safety, dict):
        safety = {"category": None, "rationale": ""}

    return Classification(
        agent=agent,
        intent=str(payload.get("intent", agent)),
        entities=entities,
        confidence=float(payload.get("confidence", 0.5) or 0.5),
        safety_verdict=safety,
        raw=payload,
    )


def _fallback(error: str) -> Classification:
    return Classification(
        agent="general_query",
        intent="unknown",
        entities={},
        confidence=0.0,
        safety_verdict={"category": None, "rationale": ""},
        raw={},
        fallback_used=True,
        error=error,
    )


# Tests inject a callable that returns the parsed dict directly (no LLM
# round-trip). Production code uses the real client.
LLMCallable = Callable[[list[dict[str, str]]], dict[str, Any]]


def classify(
    query: str,
    *,
    session: SessionState | None = None,
    user_context: dict[str, Any] | None = None,
    llm: LLMClient | LLMCallable | None = None,
) -> Classification:
    """Classify a single user turn. Never raises."""
    if not (query or "").strip():
        return _fallback("empty query")

    carryover: dict[str, Any] | None = None
    prior: list[str] = []
    if session is not None:
        prior = session.prior_user_turns()
        if session.last_intent or session.last_tickers:
            carryover = {
                "last_intent": session.last_intent,
                "last_tickers": session.last_tickers,
            }

    user_msg = _build_user_message(
        query=query,
        prior_user_turns=prior,
        user_context=user_context,
        carryover=carryover,
    )
    messages = assemble_messages(system=SYSTEM_PROMPT, user=user_msg)

    payload: dict[str, Any] | None = None
    try:
        if llm is None:
            client = get_llm_client()
            payload = client.complete_json(messages, json_schema=CLASSIFIER_SCHEMA)
        elif isinstance(llm, LLMClient):
            payload = llm.complete_json(messages, json_schema=CLASSIFIER_SCHEMA)
        else:
            payload = llm(messages)
    except LLMError as exc:
        logger.warning("LLM classifier failed: %s", exc)
        return _fallback(str(exc))
    except Exception as exc:
        logger.exception("Unexpected classifier failure")
        return _fallback(f"unexpected: {exc}")

    if not isinstance(payload, dict):
        return _fallback("non-dict LLM payload")

    return _coerce(payload)
