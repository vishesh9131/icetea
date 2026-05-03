"""
SSE serialization.

We do not use sse-starlette directly here because we want full control
over event names and payload shape, and the protocol itself is tiny.
The pipeline yields normalized event dicts; this module turns them into
the wire-format frames a browser EventSource consumer expects.
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator


def _encode(event_name: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False)
    # Each SSE frame: `event: <name>\n` then one or more `data: <line>\n`
    # then a blank line. We send single-line JSON so we never have to
    # worry about embedded newlines splitting frames.
    return f"event: {event_name}\ndata: {body}\n\n"


def event_to_sse(event: dict[str, Any]) -> str:
    """Map a pipeline event dict to an SSE frame."""
    etype = event.get("type", "message")
    if etype == "data":
        # narrative streaming — keep payload minimal so the browser can
        # concatenate `delta` cheaply
        return _encode("token", {"delta": event.get("delta", "")})
    if etype == "structured":
        return _encode("structured", event.get("payload", {}))
    if etype == "meta":
        return _encode("meta", {k: v for k, v in event.items() if k != "type"})
    if etype == "error":
        return _encode("error", {k: v for k, v in event.items() if k != "type"})
    if etype == "done":
        return _encode("done", {k: v for k, v in event.items() if k != "type"})
    return _encode(etype, event)


async def stream_events(events: AsyncIterator[dict[str, Any]]) -> AsyncIterator[str]:
    async for event in events:
        yield event_to_sse(event)
