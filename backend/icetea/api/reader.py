"""In-app article reader.

The frontend dock has a READER tile that previews article bodies without
ever opening an external browser tab. This module is the backend half of
that flow: it wraps ``toolkit_fetch_url`` so we get SSRF filtering,
HTTPS-only enforcement, and HTML -> plain-text extraction for free.

We cache the extracted text per URL for 15 minutes because the news panel
will refetch the same article when the user clicks the same headline
twice in quick succession (very common during a market session).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_TTL_S = 900.0     # 15 min - articles rarely change after publish
_MAX_CACHE = 64
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = asyncio.Lock()


def _evict_if_full() -> None:
    if len(_cache) <= _MAX_CACHE:
        return
    # drop the oldest entry
    oldest_url = min(_cache.items(), key=lambda kv: kv[1][0])[0]
    _cache.pop(oldest_url, None)


def _fetch_blocking(url: str) -> dict[str, Any]:
    """Sync call into toolkit_fetch_article - run in to_thread."""
    # deferred import - module-level would pull the orchestration graph
    from ..orchestration.toolkits import web_tools as wt

    res = wt.toolkit_fetch_article(url)
    return {
        "ok": bool(res.get("ok", False)),
        "url": res.get("url") or url,
        "text": str(res.get("text") or ""),
        "title": res.get("title"),
        "note": res.get("note"),
        "http_status": res.get("http_status"),
        "fetched_at": time.time(),
    }


async def fetch_article(url: str) -> dict[str, Any]:
    """Cached, async-safe article fetch."""
    key = url.strip()
    if not key:
        return {"ok": False, "url": url, "text": "", "note": "empty_url"}

    now = time.time()
    cached = _cache.get(key)
    if cached and (now - cached[0]) < _CACHE_TTL_S:
        return cached[1]

    async with _cache_lock:
        cached = _cache.get(key)
        if cached and (time.time() - cached[0]) < _CACHE_TTL_S:
            return cached[1]
        try:
            payload = await asyncio.to_thread(_fetch_blocking, key)
        except Exception as exc:
            logger.warning("reader fetch failed for %s: %s", key, exc)
            payload = {"ok": False, "url": key, "text": "", "note": f"fetch_error:{exc}"}
        _cache[key] = (time.time(), payload)
        _evict_if_full()
        return payload


def reset_cache_for_tests() -> None:
    _cache.clear()
