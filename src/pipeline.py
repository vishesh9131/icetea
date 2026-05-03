"""
Pipeline orchestrator.

One entrypoint, `process_query`, that runs:

    safety guard  ->  classifier  ->  agent  ->  events

It yields normalized event dicts that the HTTP layer turns into SSE frames.
The HTTP layer doesn't reach into safety/classifier/agents directly — only
this module does. Keeps the system testable without a webserver.

Errors are events, not exceptions. The only thing that can stop the loop
mid-stream is the global timeout — and that emits a final `error` event
before closing.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, AsyncIterator

from . import safety
from .agents.registry import get_agent, is_implemented
from .classifier import classify
from .config import get_settings
from .llm import LLMClient
from .session import SessionState, get_session_store


logger = logging.getLogger(__name__)


def _meta_event(**fields: Any) -> dict[str, Any]:
    return {"type": "meta", **fields}


def _error_event(message: str, *, code: str = "internal_error") -> dict[str, Any]:
    return {"type": "error", "code": code, "message": message}


async def process_query(
    *,
    query: str,
    session_id: str,
    user_context: dict[str, Any] | None = None,
    llm: LLMClient | None = None,
    settings=None,
) -> AsyncIterator[dict[str, Any]]:
    """Run the full pipeline. Yields event dicts.

    Event types:
        meta       - progress / debug; metadata events.
        data       - narrative text token (delta to append to UI buffer).
        structured - the agent's structured payload.
        done       - terminal marker.
        error      - terminal marker for failures.
    """
    settings = settings or get_settings()
    user_ctx = user_context or {}
    request_id = str(uuid.uuid4())
    started = time.perf_counter()

    yield _meta_event(stage="received", request_id=request_id, session_id=session_id)

    # ---------- safety ----------
    verdict = safety.check(query)
    if verdict.blocked:
        yield _meta_event(
            stage="safety",
            blocked=True,
            category=verdict.category,
            latency_ms=verdict.latency_ms,
        )
        # Send the refusal as both narrative + structured so clients can pick.
        yield {"type": "data", "delta": verdict.message or ""}
        yield {
            "type": "structured",
            "payload": {
                "agent": "safety_guard",
                "blocked": True,
                "category": verdict.category,
                "message": verdict.message,
            },
        }
        yield {"type": "done", "request_id": request_id, "blocked": True}
        return

    yield _meta_event(stage="safety", blocked=False, latency_ms=verdict.latency_ms)

    # ---------- classifier ----------
    store = get_session_store()
    state: SessionState = store.get(session_id)
    store.append_turn(session_id, role="user", content=query)

    try:
        classification = await asyncio.wait_for(
            asyncio.to_thread(
                classify,
                query,
                session=state,
                user_context=user_ctx,
                llm=llm,
            ),
            timeout=min(settings.request_timeout_s, 90.0),
        )
    except asyncio.TimeoutError:
        yield _error_event("classifier_timeout", code="timeout")
        yield {"type": "done", "request_id": request_id, "blocked": False}
        return
    except Exception as exc:
        logger.exception("Pipeline: classifier crashed")
        yield _error_event(f"classifier_error: {exc}", code="classifier_error")
        yield {"type": "done", "request_id": request_id, "blocked": False}
        return

    yield _meta_event(
        stage="classified",
        agent=classification.agent,
        intent=classification.intent,
        confidence=classification.confidence,
        fallback_used=classification.fallback_used,
        implemented=is_implemented(classification.agent),
        safety_verdict=classification.safety_verdict,
    )

    store.update_carryover(
        session_id,
        intent=classification.agent,
        tickers=classification.entities.get("tickers") or [],
    )

    # ---------- routed agent ----------
    agent = get_agent(classification.agent)

    response_buffer: list[str] = []
    structured_payload: dict[str, Any] | None = None

    try:
        agent_iter = agent.run(
            query=query,
            user_context=user_ctx,
            classification={
                "agent": classification.agent,
                "intent": classification.intent,
                "entities": classification.entities,
                "confidence": classification.confidence,
            },
            llm=llm,
        )
        async for event in _with_timeout(agent_iter, settings.request_timeout_s, started):
            if event.get("type") == "data":
                response_buffer.append(event.get("delta", ""))
            elif event.get("type") == "structured":
                structured_payload = event.get("payload")
            yield event
    except asyncio.TimeoutError:
        yield _error_event("pipeline_timeout", code="timeout")
        yield {"type": "done", "request_id": request_id, "blocked": False}
        return
    except Exception as exc:
        logger.exception("Pipeline: agent crashed")
        yield _error_event(f"agent_error: {exc}", code="agent_error")
        yield {"type": "done", "request_id": request_id, "blocked": False}
        return

    if response_buffer:
        store.append_turn(session_id, role="assistant", content="".join(response_buffer))

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    yield _meta_event(stage="complete", latency_ms=elapsed_ms)
    yield {
        "type": "done",
        "request_id": request_id,
        "blocked": False,
        "agent": classification.agent,
        "implemented": is_implemented(classification.agent),
        "structured_present": structured_payload is not None,
    }


async def _with_timeout(
    aiter: AsyncIterator[dict[str, Any]],
    total_timeout_s: float,
    started: float,
) -> AsyncIterator[dict[str, Any]]:
    """Yield events while honouring the per-request timeout."""
    while True:
        remaining = total_timeout_s - (time.perf_counter() - started)
        if remaining <= 0:
            raise asyncio.TimeoutError()
        try:
            event = await asyncio.wait_for(_anext(aiter), timeout=remaining)
        except StopAsyncIteration:
            return
        yield event


async def _anext(aiter: AsyncIterator[Any]) -> Any:
    return await aiter.__anext__()
