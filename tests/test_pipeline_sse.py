"""End-to-end pipeline + SSE tests using the in-process FastAPI app."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api import routes as routes_mod
from src.pipeline import process_query
from src.session import InMemorySessionStore


def _parse_sse(body: str) -> list[dict]:
    """Naive SSE parser: returns a list of {event, data} dicts."""
    events: list[dict] = []
    current: dict[str, str] = {}
    for line in body.splitlines():
        if not line:
            if current:
                events.append(current)
                current = {}
            continue
        if line.startswith("event:"):
            current["event"] = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            current["data"] = line.split(":", 1)[1].strip()
    if current:
        events.append(current)
    return events


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["llm_provider"] in {"openai", "vllm"}


def _collect(events):
    out: list[dict] = []
    import asyncio

    async def _run():
        async for e in events:
            out.append(e)
    asyncio.run(_run())
    return out


def test_pipeline_blocks_harmful_query():
    """Safety guard runs first; classifier/agent never invoked."""
    events = process_query(
        query="guarantee me 30% returns on this portfolio",
        session_id="sess_block",
        user_context={"user_id": "usr_001", "positions": []},
        llm=lambda _msgs: pytest.fail("classifier should not be called when blocked"),
    )
    out = _collect(events)
    types = [e["type"] for e in out]
    assert "structured" in types
    structured = next(e for e in out if e["type"] == "structured")
    assert structured["payload"]["agent"] == "safety_guard"
    assert structured["payload"]["blocked"] is True
    done = next(e for e in out if e["type"] == "done")
    assert done["blocked"] is True


def test_pipeline_routes_to_portfolio_health(load_user, fake_llm):
    user = load_user("usr_003")
    events = process_query(
        query="how is my portfolio doing",
        session_id="sess_ph",
        user_context=user,
        llm=fake_llm,
    )
    out = _collect(events)
    classified = next(e for e in out if e["type"] == "meta" and e.get("stage") == "classified")
    assert classified["agent"] == "portfolio_health"
    structured = next(e for e in out if e["type"] == "structured")
    assert "concentration_risk" in structured["payload"]
    assert structured["payload"]["concentration_risk"]["top_holding"] == "NVDA"


def test_pipeline_stub_agent_returns_not_implemented(load_user, fake_llm):
    user = load_user("usr_001")
    events = process_query(
        query="recommend a dividend ETF",
        session_id="sess_stub",
        user_context=user,
        llm=fake_llm,
    )
    out = _collect(events)
    structured = next(e for e in out if e["type"] == "structured")
    payload = structured["payload"]
    assert payload["agent"] == "product_recommendation"
    assert payload["implemented"] is False
    assert "not implemented" in payload["message"].lower()


def test_sse_endpoint_emits_well_formed_frames(monkeypatch, client, fake_llm, load_user):
    """Hit the real HTTP layer and parse the SSE stream."""
    # the endpoint reads from the global classifier; inject our fake_llm
    # by monkeypatching the pipeline's classifier call site.
    from src import pipeline

    real_classify = pipeline.classify

    def _patched(query, *, session=None, user_context=None, llm=None):
        return real_classify(query, session=session, user_context=user_context, llm=fake_llm)

    monkeypatch.setattr(pipeline, "classify", _patched)

    user = load_user("usr_001")
    body = {
        "query": "hi",
        "session_id": "sess_http",
        "user_context": user,
    }
    with client.stream("POST", "/v1/chat", json=body) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body_text = "".join(chunk for chunk in resp.iter_text())

    events = _parse_sse(body_text)
    assert events, "No SSE events received"
    names = {e.get("event") for e in events}
    assert "meta" in names
    assert "done" in names
    # every data line is valid JSON
    for e in events:
        if "data" in e:
            json.loads(e["data"])
