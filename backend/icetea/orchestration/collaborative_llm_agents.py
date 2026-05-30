"""Separate LLM inference per collaborative agent — distinct prompts + contexts.

Tools stay deterministic (same bundles MCP/supervisor already compute); each
specialist runs its own ``complete_json`` pass so disagreement can emerge.
Chair streams plain prose so the user sees non-JSON synthesis."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from ..llm import LLMClient, LLMError, assemble_messages

from ..safety import MODEL_INJECTION_GUARD

logger = logging.getLogger(__name__)

# OpenAI strict json_schema wants this shape
_AGENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "title": "collab_agent_turn",
    "properties": {
        "reasoning_trace": {"type": "array", "items": {"type": "string"}},
        "confidence_0_100": {"type": "integer", "minimum": 0, "maximum": 100},
        "stance_headline": {"type": "string"},
        "answer": {"type": "string"},
        "abstain": {"type": "boolean"},
        "abstain_reason": {"type": "string"},
    },
    "required": [
        "reasoning_trace",
        "confidence_0_100",
        "stance_headline",
        "answer",
        "abstain",
        "abstain_reason",
    ],
}

SYS_PORTFOLIO = """You are the Portfolio Analyst agent in a multi-agent panel.

Objective: STRUCTURAL lens only — weights, overlap between lines, stated risk label vs book, diversification gaps. Numbers come only from the JSON bundle.
Rules:
- Do not invent positions or prices not in the bundle.
- reasoning_trace: 2–5 bullets, facts -> stance only.
- stance_headline: one line, book-structure voice (not macro drama, not tape timing).
- answer: max ~90 words, for other agents only (chair writes the investor essay). No Fed/recession essay here — that is Market's lane.
- You have NOT seen live tape yet — do not sound like a tape trader.
- Vocabulary you should NOT lean on as your main thesis: "trim", "monitor closely", "strong sell" — say structure (concentration, overlap, sleeve gaps) instead.
- If user_question is only chat/session recap or meta (no holdings math), abstain=true, abstain_reason one line, answer empty or "n/a".
""" + "\n\n" + MODEL_INJECTION_GUARD

SYS_MARKET = """You are the Market Analyst agent.

Objective: MACRO / TAPE lens only — levels, sector, recent returns, liquidity tone from the JSON facts.
You receive portfolio_facts_numeric (numbers only) for sizing context — do not copy Portfolio's prose; do not give sizing advice or re-hash overlap tables in long form.
Rules:
- Independent reasoning — Market runs before Risk/Momentum see your full text; keep answer tight so later agents dont parrot you.
- reasoning_trace: 2–5 bullets.
- answer: max ~90 words. No "rebalance" or "trim the book" as the headline — that is Portfolio/Risk wording; you cite tape and regime only.
- If return data is missing, say so and lower confidence.
- If user_question is only about conversation memory or prior chat turns (no ticker/market substance), abstain=true and explain in abstain_reason — do not fabricate tape commentary.
""" + "\n\n" + MODEL_INJECTION_GUARD

SYS_RISK = """You are the Risk / Skeptic agent.

Objective: CONSERVATIVE lens — sizing vs profile, gap risk, scenario stress, where optimism might be wrong. You are NOT the momentum or tape-timing voice.
You receive numeric shared_facts plus SHORT peer outlines (not full essays) — do not restate their paragraphs in new adjectives; add at least one risk angle they did not spell out, or explicitly agree with one narrow point only.
Rules:
- Do NOT open with tape momentum language as your headline — that belongs to Momentum. Do NOT lead with tactical "when to trim" as if you were a trader — say why risk is elevated or tolerable in structure/terms.
- Be willing to disagree with Market if tape looks fine but sizing is reckless; be willing to disagree with Portfolio if book looks tame but macro window is ugly (one sentence max on macro, then back to book).
- reasoning_trace must show at least one explicit pushback or caveat that is not generic "diversify".
- answer: max ~100 words.
- If user_question is purely session/meta/recap, abstain=true — risk lens does not apply.
""" + "\n\n" + MODEL_INJECTION_GUARD

SYS_MOMENTUM = """You are the Momentum / Trend agent.

Objective: TACTICAL tape lens — trend persistence, relative strength, horizon for mean-reversion vs trend continuation. You are NOT the primary concentration cop; Risk already owns that.
You receive full numeric shared_facts plus portfolio_peer_outline and market_peer_outline (stance + confidence + abstain flags only) — reason mainly from shared_facts; do NOT treat outlines as prose to echo.
Rules:
- Forbidden as your stance_headline or first sentence: "trim", "rebalance", "concentration warning", "manage risk", "monitor closely" as the MAIN thesis — those read as Risk/Portfolio. You may mention sizing in ONE short clause AFTER you state the tape read.
- You may disagree with Risk if returns/sector context support patience; say why with numbers not rhetoric.
- reasoning_trace: 2–5 bullets tied to return/sector facts.
- answer: max ~90 words.
- If user_question is about chat history or session memory only, abstain=true — say momentum agent has nothing to add.
""" + "\n\n" + MODEL_INJECTION_GUARD

SYS_CHAIR = """You write the ONLY text the retail investor will read from this step.

Input is structured analyst notes (JSON-shaped facts + short opinions). Treat it as confidential reasoning — never quote JSON keys, routing labels, or words like "agent", "panel", "tool", "schema".

If an analyst block has abstain=true, skip their substance entirely — do not invent portfolio or tape takes on their behalf.

Preserve DISTINCT voices in plain English (book structure vs tape vs risk vs momentum) — do not flatten four specialists into one generic "be careful and diversify" paragraph. If two analysts sounded similar in the notes, still separate what the BOOK implies vs what the TAPE implies vs what RISK adds that is NEW.

Output plain prose only: calm, specific, educational. Round percentages sensibly in speech (e.g. "~8.5%" not 8.523). Mention disagreement honestly when views clash.

Cover holdings concentration vs recent tape tone (from non-abstaining voices only), then balanced takeaway with non-prescriptive options (trim gradually, diversify, caps, wait-and-watch). Never expose middleware.

Educational context only — not personalized investment advice.

Stay under ~300 words. Do not repeat the same numeric fact block three times — cite each key number at most once unless resolving a disagreement.
""" + "\n\n" + MODEL_INJECTION_GUARD


def _compact_agent(
    obj: dict[str, Any],
    *,
    answer_max_chars: int | None = 320,
) -> dict[str, Any]:
    ans = str(obj.get("answer") or "")
    if answer_max_chars is not None and len(ans) > int(answer_max_chars):
        cut = max(0, int(answer_max_chars) - 1)
        ans = ans[:cut].rsplit(" ", 1)[0] + "…"
    return {
        "stance_headline": obj.get("stance_headline"),
        "confidence_0_100": obj.get("confidence_0_100"),
        "answer": ans,
        "reasoning_trace": (obj.get("reasoning_trace") or [])[:6],
        "abstain": bool(obj.get("abstain")),
        "abstain_reason": str(obj.get("abstain_reason") or "")[:200],
    }


def _peer_outline_for_momentum(obj: dict[str, Any]) -> dict[str, Any]:
    """Headline-only handoff so Momentum doesnt re-read long mirrored peer prose."""
    return {
        "stance_headline": obj.get("stance_headline"),
        "confidence_0_100": obj.get("confidence_0_100"),
        "abstain": bool(obj.get("abstain")),
    }


def _json_for_llm(blob: dict[str, Any]) -> str:
    """Tight wire to model — avoids pretty-print token waste."""
    return json.dumps(blob, ensure_ascii=False, separators=(",", ":"), default=str)


async def _infer_agent(
    llm: LLMClient,
    *,
    system: str,
    user_blob: dict[str, Any],
    temperature: float,
    max_tokens: int = 760,
) -> dict[str, Any]:
    """One structured LLM pass (blocking SDK wrapped for async pipeline)."""

    def _call() -> dict[str, Any]:
        messages = assemble_messages(
            system=system,
            user=_json_for_llm(user_blob),
        )
        return llm.complete_json(
            messages,
            json_schema=_AGENT_SCHEMA,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    try:
        raw = await asyncio.to_thread(_call)
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(str(exc)) from exc

    if not isinstance(raw, dict):
        raise LLMError("collab agent expected dict JSON")
    # models ocasionally drift keys — normalize lightly
    trace = raw.get("reasoning_trace")
    if not isinstance(trace, list):
        trace = [str(trace)] if trace is not None else []
    trace = [str(x).strip() for x in trace if str(x).strip()]
    if not trace:
        trace = ["(model omitted trace)"]
    try:
        conf = int(raw.get("confidence_0_100", 50))
    except (TypeError, ValueError):
        conf = 50
    conf = max(0, min(100, conf))
    abstain = bool(raw.get("abstain"))
    abstain_reason = str(raw.get("abstain_reason") or "").strip()
    ans = str(raw.get("answer") or "").strip() or str(raw.get("stance_headline") or "")
    if abstain and not ans:
        ans = "n/a"
    return {
        "reasoning_trace": trace,
        "confidence_0_100": conf,
        "stance_headline": str(raw.get("stance_headline") or "").strip() or "No headline",
        "answer": ans,
        "abstain": abstain,
        "abstain_reason": abstain_reason,
    }


async def run_portfolio_llm(
    llm: LLMClient, *, query: str, portfolio_tool_bundle: dict[str, Any], temperature: float = 0.38
) -> dict[str, Any]:
    blob = {"user_question": query, "portfolio_tool_bundle": portfolio_tool_bundle}
    return await _infer_agent(llm, system=SYS_PORTFOLIO, user_blob=blob, temperature=temperature)


async def run_market_llm(
    llm: LLMClient,
    *,
    query: str,
    portfolio_facts: dict[str, Any],
    market_tool_bundle: dict[str, Any],
    temperature: float = 0.38,
) -> dict[str, Any]:
    blob = {
        "user_question": query,
        "portfolio_facts_numeric": portfolio_facts,
        "market_tool_bundle": market_tool_bundle,
    }
    return await _infer_agent(llm, system=SYS_MARKET, user_blob=blob, temperature=temperature)


async def run_risk_llm(
    llm: LLMClient,
    *,
    query: str,
    shared_facts: dict[str, Any],
    portfolio_analyst: dict[str, Any],
    market_analyst: dict[str, Any],
    temperature: float = 0.48,
) -> dict[str, Any]:
    blob = {
        "user_question": query,
        "shared_facts": shared_facts,
        "portfolio_analyst": _compact_agent(portfolio_analyst, answer_max_chars=240),
        "market_analyst": _compact_agent(market_analyst, answer_max_chars=240),
    }
    return await _infer_agent(llm, system=SYS_RISK, user_blob=blob, temperature=temperature)


async def run_momentum_llm(
    llm: LLMClient,
    *,
    query: str,
    shared_facts: dict[str, Any],
    portfolio_analyst: dict[str, Any],
    market_analyst: dict[str, Any],
    temperature: float = 0.48,
) -> dict[str, Any]:
    blob = {
        "user_question": query,
        "shared_facts": shared_facts,
        "portfolio_peer_outline": _peer_outline_for_momentum(portfolio_analyst),
        "market_peer_outline": _peer_outline_for_momentum(market_analyst),
    }
    return await _infer_agent(llm, system=SYS_MOMENTUM, user_blob=blob, temperature=temperature)


async def stream_chair_answer(
    llm: LLMClient,
    *,
    query: str,
    portfolio_analyst: dict[str, Any],
    market_analyst: dict[str, Any],
    risk_analyst: dict[str, Any],
    momentum_analyst: dict[str, Any],
    temperature: float = 0.55,
    max_tokens: int = 1100,
) -> AsyncIterator[str]:
    pack = {
        "user_question": query,
        "portfolio_analyst": _compact_agent(portfolio_analyst, answer_max_chars=380),
        "market_analyst": _compact_agent(market_analyst, answer_max_chars=380),
        "risk_agent": _compact_agent(risk_analyst, answer_max_chars=380),
        "momentum_agent": _compact_agent(momentum_analyst, answer_max_chars=380),
    }
    messages = assemble_messages(
        system=SYS_CHAIR,
        user=_json_for_llm(pack),
    )
    try:
        async for piece in llm.stream_text(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield piece
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(str(exc)) from exc


_DISCUSSION_SYS: dict[str, str] = {
    "portfolio": """You are the Portfolio Analyst in a multi-agent MESSAGE THREAD.
Other specialists may already have spoken in thread_so_far — read their points; you may answer them BY ROLE NAME (Market Analyst, Risk, etc.).
Rules: stay grounded in numeric_facts; do not invent holdings; one focused reply (not a full essay).
You MUST be quantitatively opinionated:
- Include at least 2 concrete numbers from numeric_facts (%, counts, windows, etc.).
- If cycle>=2, add one NEW numeric angle not already stated in thread_so_far (e.g., top2 concentration, stress-case hit, threshold).
Output the SAME JSON schema as other collab agents (reasoning_trace, confidence, stance_headline, answer, abstain, abstain_reason).
If the user question is pure chat recap with no portfolio substance, abstain=true.
"""
    + "\n\n"
    + MODEL_INJECTION_GUARD,
    "market": """You are the Market Analyst in a multi-agent MESSAGE THREAD.
thread_so_far lists prior agent messages — respond directly to peers when useful; disagree if tape evidence supports it.
Use numeric_facts + context; do not invent prices. Same JSON schema as other collab agents.
You MUST be quantitatively opinionated:
- Include at least 2 numbers (price, return window %, sector benchmark stub fields, etc.). If returns are missing, quantify the missingness ("no 21d return").
- If cycle>=2, update one prior claim by tightening it (e.g., "return ~X% not just 'strong'") or state a regime probability range (qualitative is not enough).
If the thread is off-topic for tape, abstain=true.
"""
    + "\n\n"
    + MODEL_INJECTION_GUARD,
    "tax_math": """You are the Tax / lots analyst in a multi-agent MESSAGE THREAD.
thread_so_far may show Portfolio or Market pushback — engage politely with substance; remind limits of stub math.
Same JSON schema. If no tax-relevant facts, abstain=true.
"""
    + "\n\n"
    + MODEL_INJECTION_GUARD,
    "risk": """You are the Risk / skeptic agent in a multi-agent MESSAGE THREAD.
CONSERVATIVE voice: sizing, shocks, gap risk — not tape-timing or momentum headlines.
Challenge optimistic tape takes or reckless sizing; do not copy Market wording as your opening.
Same JSON schema; answer stays under ~90 words.
You MUST be quantitatively opinionated:
- Include at least 2 numbers from numeric_facts (concentration %, stress-case hit %, horizon windows).
- If cycle>=2, explicitly revise a prior risk view with a numeric delta (tighter/wider stress range, different trigger threshold), or say "no update" with one numeric justification.
"""
    + "\n\n"
    + MODEL_INJECTION_GUARD,
    "momentum": """You are the Momentum / trend agent in a multi-agent MESSAGE THREAD.
TACTICAL tape voice: trend persistence, relative strength — not the primary concentration lecture (Risk owns that).
You may push back on Risk with return/sector facts; do not open with "trim" / "monitor closely" as your thesis line.
Same JSON schema; answer stays under ~90 words.
You MUST be quantitatively opinionated:
- Include at least 2 numbers from numeric_facts (return %, price, window length).
- If cycle>=2, make one numeric bet: what would change your mind (e.g., "if 21d return flips below -X%").
"""
    + "\n\n"
    + MODEL_INJECTION_GUARD,
}

SYS_CHAIR_THREAD = """You chair a multi-agent DISCUSSION. Inputs: user_question, full thread (agents quoted each other), numeric_facts.
Write the ONLY investor-facing closing: where the team agreed, where they clashed, and 3–5 practical non-prescriptive options (trim, diversify, wait, caps, tax-aware timing). Never quote JSON keys or internal labels like 'agent' or 'schema'. Plain prose, calm tone, under ~320 words.
Keep BOOK vs TAPE vs RISK vs MOMENTUM as distinct threads in the prose — do not collapse into one generic warning paragraph. Cite each key number at most once unless two agents disagree on it.
Educational context only — not personalized investment advice.
""" + "\n\n" + MODEL_INJECTION_GUARD


def _trim_transcript_for_chair(
    transcript: list[dict[str, Any]],
    *,
    text_max: int = 520,
) -> list[dict[str, Any]]:
    """Stops chair prompt from re-ingesting huge duplicate thread blobs."""
    out: list[dict[str, Any]] = []
    for row in transcript:
        r = dict(row)
        t = str(r.get("text") or "")
        if len(t) > text_max:
            t = t[: max(0, text_max - 1)].rsplit(" ", 1)[0] + "…"
        r["text"] = t
        out.append(r)
    return out


async def run_discussion_turn(
    llm: LLMClient,
    *,
    speaker_role: str,
    query: str,
    transcript: list[dict[str, Any]],
    shared_facts: dict[str, Any],
    extra_context: dict[str, Any],
    cycle: int = 1,
    temperature: float = 0.44,
) -> dict[str, Any]:
    system = _DISCUSSION_SYS.get(speaker_role) or _DISCUSSION_SYS["risk"]
    blob = {
        "user_question": query,
        "cycle": int(cycle),
        "thread_so_far": _trim_transcript_for_chair(transcript, text_max=480),
        "numeric_facts": shared_facts,
        "extra_context": extra_context,
    }
    return await _infer_agent(llm, system=system, user_blob=blob, temperature=temperature)


async def stream_chair_from_transcript(
    llm: LLMClient,
    *,
    query: str,
    transcript: list[dict[str, Any]],
    shared_facts: dict[str, Any],
    temperature: float = 0.52,
    max_tokens: int = 1000,
) -> AsyncIterator[str]:
    pack = {
        "user_question": query,
        "agent_thread": _trim_transcript_for_chair(transcript, text_max=520),
        "numeric_facts": shared_facts,
    }
    messages = assemble_messages(
        system=SYS_CHAIR_THREAD,
        user=_json_for_llm(pack),
    )
    try:
        async for piece in llm.stream_text(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield piece
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(str(exc)) from exc
