"""
Small streaming helper shared by all narrative agents.

Reason this exists: every agent that streams a free-form answer used to do
exactly the same `async for piece in client.stream_text(...)` dance. When we
added a separate chain-of-thought channel ("thinking"), each call site needed
the same fan-out logic - check whether the client supports tagged streaming,
fall back gracefully if it does not, branch the chunks into either a `data`
or `thinking` SSE event. Centralising it here keeps the seven agent files
free of that boilerplate and gives us one place to fix bugs.

Yielded tuples:
    ("think",   piece)  ->  goes into the collapsible "Thinking..." block
    ("content", piece)  ->  goes into the main answer body

Older fake LLMs in the test suite only implement `stream_text`. We detect
that case and emit everything as "content" so unit tests keep working.
"""
from __future__ import annotations

from typing import Any, AsyncIterator


async def stream_pieces(
    client: Any,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 800,
    enable_thinking: bool = True,
) -> AsyncIterator[tuple[str, str]]:
    """Yield (channel, piece) tuples from any LLM client we ship.

    Prefers `stream_text_tagged` (real OpenAICompatClient). Falls back to
    `stream_text` if the client predates the tagged API - in that case
    every chunk is reported on the "content" channel.
    """
    tagged = getattr(client, "stream_text_tagged", None)
    if tagged is not None:
        async for channel, piece in tagged(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            enable_thinking=enable_thinking,
        ):
            yield channel, piece
        return

    # Compat path: fake/older client. No thinking visible, but the answer
    # still streams normally.
    async for piece in client.stream_text(
        messages, temperature=temperature, max_tokens=max_tokens
    ):
        yield "content", piece
