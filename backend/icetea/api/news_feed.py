"""Live financial news feed for the terminal NEWS panel.

Pulls news from yfinance for a fixed market basket (indices + the user's
holdings) and dedupes by article id. Hammering yfinance per page-load is
rude so we cache per-ticker for 5 minutes and serve stale items while a
background refresh runs.

We do not synthesize, score, or summarise the stories. The UI gets exactly
the fields yfinance / yahoo finance ships, normalized to a stable shape so
the frontend doesn't have to know about content/clickThroughUrl/etc.
nesting.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, asdict
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# General market basket: the major US indices + a handful of mega-caps. Pulls
# from these get cached per-ticker so adding the user's portfolio later
# rarely costs an extra network hop for overlapping tickers.
_MARKET_BASKET: tuple[str, ...] = ("^GSPC", "^IXIC", "^DJI", "AAPL", "MSFT", "NVDA")
_PER_TICKER_TTL_S = 300.0          # 5 minutes
_MAX_RETURNED = 25


@dataclass
class NewsItem:
    id: str
    title: str
    summary: str | None
    url: str | None
    source: str | None
    image: str | None
    published_at: str | None        # ISO-8601 string from upstream
    published_ts: float | None      # unix seconds, parsed for sorting client-side
    tickers: list[str]


# per-ticker cache: { ticker -> (epoch_ts, [items]) }
_cache: dict[str, tuple[float, list[NewsItem]]] = {}
_cache_lock = asyncio.Lock()


def _iso_to_ts(s: str | None) -> float | None:
    if not s:
        return None
    try:
        # yfinance returns "2026-05-29T13:10:29Z" - python's fromisoformat handles
        # the Z suffix only on 3.11+; do a tiny normalize for older runtimes.
        from datetime import datetime
        norm = s.replace("Z", "+00:00")
        return datetime.fromisoformat(norm).timestamp()
    except Exception:
        return None


def _normalize(raw: dict[str, Any], ticker: str) -> NewsItem | None:
    """Flatten the nested yfinance shape to our stable NewsItem."""
    if not isinstance(raw, dict):
        return None
    content = raw.get("content") if isinstance(raw.get("content"), dict) else raw
    title = content.get("title") or raw.get("title")
    if not title:
        return None
    item_id = raw.get("id") or content.get("id") or title
    summary = content.get("summary") or content.get("description") or None
    ctu = content.get("clickThroughUrl") or content.get("canonicalUrl") or {}
    url = ctu.get("url") if isinstance(ctu, dict) else None
    if not url and isinstance(raw.get("link"), str):
        url = raw.get("link")
    provider = content.get("provider") or {}
    source = provider.get("displayName") if isinstance(provider, dict) else None
    thumb = content.get("thumbnail") or {}
    image = thumb.get("originalUrl") if isinstance(thumb, dict) else None
    published = content.get("pubDate") or content.get("displayTime") or raw.get("providerPublishTime")
    if isinstance(published, (int, float)):
        try:
            from datetime import datetime, timezone
            published_iso = datetime.fromtimestamp(float(published), tz=timezone.utc).isoformat()
        except Exception:
            published_iso = None
    else:
        published_iso = published if isinstance(published, str) else None
    return NewsItem(
        id=str(item_id),
        title=str(title),
        summary=str(summary) if summary else None,
        url=str(url) if url else None,
        source=str(source) if source else None,
        image=str(image) if image else None,
        published_at=published_iso,
        published_ts=_iso_to_ts(published_iso),
        tickers=[ticker],
    )


def _fetch_one_ticker_blocking(ticker: str) -> list[NewsItem]:
    """Sync yfinance call - run inside asyncio.to_thread."""
    try:
        import yfinance as yf
    except Exception as exc:
        logger.warning("yfinance unavailable for news(%s): %s", ticker, exc)
        return []
    try:
        raw = yf.Ticker(ticker).news or []
    except Exception as exc:
        logger.warning("yfinance news fetch failed for %s: %s", ticker, exc)
        return []
    out: list[NewsItem] = []
    for r in raw:
        item = _normalize(r, ticker)
        if item:
            out.append(item)
    return out


async def _get_for_ticker(ticker: str) -> list[NewsItem]:
    """Cached per-ticker fetch."""
    now = time.time()
    cached = _cache.get(ticker)
    if cached and (now - cached[0]) < _PER_TICKER_TTL_S:
        return cached[1]
    async with _cache_lock:
        # someone may have already refreshed while we waited
        cached = _cache.get(ticker)
        if cached and (time.time() - cached[0]) < _PER_TICKER_TTL_S:
            return cached[1]
        items = await asyncio.to_thread(_fetch_one_ticker_blocking, ticker)
        _cache[ticker] = (time.time(), items)
        return items


def _dedupe_and_sort(streams: Iterable[list[NewsItem]]) -> list[NewsItem]:
    """Merge multiple per-ticker streams, dedupe by article id, latest first."""
    by_id: dict[str, NewsItem] = {}
    for stream in streams:
        for it in stream:
            existing = by_id.get(it.id)
            if existing is None:
                by_id[it.id] = NewsItem(**{**asdict(it), "tickers": list(it.tickers)})
            else:
                # merge tickers if the same story showed up under multiple symbols
                merged = list(dict.fromkeys([*existing.tickers, *it.tickers]))
                by_id[it.id] = NewsItem(**{**asdict(existing), "tickers": merged})
    items = list(by_id.values())
    items.sort(key=lambda x: x.published_ts or 0.0, reverse=True)
    return items[:_MAX_RETURNED]


async def get_market_news() -> dict[str, Any]:
    streams = await asyncio.gather(*(_get_for_ticker(t) for t in _MARKET_BASKET))
    items = _dedupe_and_sort(streams)
    return {
        "as_of": time.time(),
        "scope": "market",
        "items": [asdict(i) for i in items],
    }


async def get_portfolio_news(tickers: list[str]) -> dict[str, Any]:
    cleaned = [t.strip().upper() for t in tickers if t and isinstance(t, str)]
    cleaned = [t for t in cleaned if t]
    if not cleaned:
        return {"as_of": time.time(), "scope": "portfolio", "tickers": [], "items": []}
    streams = await asyncio.gather(*(_get_for_ticker(t) for t in cleaned))
    items = _dedupe_and_sort(streams)
    return {
        "as_of": time.time(),
        "scope": "portfolio",
        "tickers": cleaned,
        "items": [asdict(i) for i in items],
    }


def reset_cache_for_tests() -> None:
    _cache.clear()
