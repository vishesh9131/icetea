"""
Session memory.

In-memory store keyed by session_id. Holds the last N user/assistant turns
plus a small "carryover" struct (the most recent ticker(s), the most recent
intent) so the classifier can resolve follow-ups like "what about Apple?"
or "should I sell some?".

Why in-memory: this assignment is a single-process slice of the spine.
Wiring Postgres or Redis here would add a moving part without changing
how the agent reasons. The store sits behind a tiny interface
(`SessionStore`) so swapping in `RedisSessionStore` later is a one-file
change. Documented in the README.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Iterable, Protocol


# Cap how many user turns we keep — long histories blow the LLM context
# budget without adding signal for follow-up resolution.
DEFAULT_MAX_TURNS = 8


@dataclass
class Turn:
    role: str  # "user" | "assistant"
    content: str
    ts: float = field(default_factory=time.time)


@dataclass
class SessionState:
    session_id: str
    turns: Deque[Turn]
    last_intent: str | None = None
    last_tickers: list[str] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    def append(self, role: str, content: str) -> None:
        self.turns.append(Turn(role=role, content=content))
        self.updated_at = time.time()

    def history_for_llm(self) -> list[dict[str, str]]:
        return [{"role": t.role, "content": t.content} for t in self.turns]

    def prior_user_turns(self) -> list[str]:
        return [t.content for t in self.turns if t.role == "user"][:-1]


class SessionStore(Protocol):
    def get(self, session_id: str) -> SessionState: ...
    def update_carryover(self, session_id: str, *, intent: str | None, tickers: Iterable[str]) -> None: ...
    def append_turn(self, session_id: str, role: str, content: str) -> None: ...
    def reset(self, session_id: str) -> None: ...


class InMemorySessionStore:
    def __init__(self, max_turns: int = DEFAULT_MAX_TURNS, ttl_s: int = 6 * 3600) -> None:
        self._max_turns = max_turns
        self._ttl_s = ttl_s
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionState] = {}

    def _evict_stale(self) -> None:
        # cheap, opportunistic GC. nothing fancy.
        now = time.time()
        dead = [sid for sid, s in self._sessions.items() if now - s.updated_at > self._ttl_s]
        for sid in dead:
            self._sessions.pop(sid, None)

    def get(self, session_id: str) -> SessionState:
        with self._lock:
            self._evict_stale()
            state = self._sessions.get(session_id)
            if state is None:
                state = SessionState(
                    session_id=session_id,
                    turns=deque(maxlen=self._max_turns * 2),  # role pairs
                )
                self._sessions[session_id] = state
            return state

    def update_carryover(
        self,
        session_id: str,
        *,
        intent: str | None,
        tickers: Iterable[str],
    ) -> None:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return
            if intent:
                state.last_intent = intent
            t_list = list(tickers or [])
            if t_list:
                state.last_tickers = t_list

    def append_turn(self, session_id: str, role: str, content: str) -> None:
        state = self.get(session_id)
        with self._lock:
            state.append(role, content)

    def reset(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


# Process-global default. Swap it out in tests if you need isolation.
_default_store: InMemorySessionStore | None = None


def get_session_store() -> InMemorySessionStore:
    global _default_store
    if _default_store is None:
        _default_store = InMemorySessionStore()
    return _default_store


def reset_session_store() -> None:
    global _default_store
    _default_store = None
