"""Live ticker tape feed for the front-end header ribbon.

The terminal UI scrolls a strip of quotes across the header. We resisted the
temptation to hardcode the numbers because the operator notices the moment a
"live" terminal shows last week's prices. This module pulls a fixed basket
(major US indices, FX, commodities, the 10Y yield) from yfinance with a
short TTL cache so we dont hammer the upstream once per page load.

Failure modes are first-class: if yfinance is unreachable, or a single
ticker errors, we return what we have plus a stale flag on the response so
the UI can dim the ribbon. We never raise out to the route handler.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, asdict
from typing import Any

logger = logging.getLogger(__name__)

# Basket: (display symbol, yfinance ticker, optional unit suffix shown to user).
# Order matters - this is the order the ribbon scrolls in.
_BASKET: list[tuple[str, str, str | None]] = [
    ("SPX",   "^GSPC",    None),
    ("NDX",   "^IXIC",    None),
    ("DJI",   "^DJI",     None),
    ("AAPL",  "AAPL",     None),
    ("MSFT",  "MSFT",     None),
    ("NVDA",  "NVDA",     None),
    ("GOOGL", "GOOGL",    None),
    ("AMZN",  "AMZN",     None),
    ("TSLA",  "TSLA",     None),
    ("BTC",   "BTC-USD",  None),
    ("EUR",   "EURUSD=X", None),
    ("GBP",   "GBPUSD=X", None),
    ("JPY",   "JPY=X",    None),
    ("GOLD",  "GC=F",     None),
    ("WTI",   "CL=F",     None),
    ("US10Y", "^TNX",     "%"),
]

# 45s is short enough that the strip feels alive, long enough that 16 tickers
# x 1 reload doesnt count as abusive when a tab is left open all day.
_CACHE_TTL_S = 45.0


@dataclass
class TapeItem:
    sym: str
    yf: str
    last: float | None
    change_pct: float | None
    unit: str | None = None
    error: str | None = None


_cache: dict[str, Any] = {"ts": 0.0, "items": None, "stale": True}
_cache_lock = asyncio.Lock()


def _fetch_one(yf_ticker: str) -> tuple[float | None, float | None, str | None]:
    """Return (last, change_pct, err). Best-effort, never raises."""
    try:
        import yfinance as yf  # heavy, deferred
    except Exception as exc:
        return (None, None, f"yfinance unavailable: {exc}")

    try:
        t = yf.Ticker(yf_ticker)
        fi = getattr(t, "fast_info", None)
        last = None
        prev = None
        if fi is not None:
            # fast_info object attrs differ slightly across yfinance versions
            last = getattr(fi, "last_price", None) or getattr(fi, "lastPrice", None)
            prev = getattr(fi, "previous_close", None) or getattr(fi, "previousClose", None)
        # fast_info often returns None for FX / futures - fall back to recent history
        if last is None or prev is None:
            hist = t.history(period="5d")
            closes = hist["Close"].dropna() if not hist.empty else None
            if closes is not None and len(closes) >= 2:
                last = float(closes.iloc[-1])
                prev = float(closes.iloc[-2])
            elif closes is not None and len(closes) == 1:
                last = float(closes.iloc[-1])
                prev = last  # no change pct possible
        if last is None:
            return (None, None, "no price")
        change_pct = None
        if prev not in (None, 0):
            try:
                change_pct = (float(last) - float(prev)) / float(prev) * 100.0
            except Exception:
                change_pct = None
        return (float(last), change_pct, None)
    except Exception as exc:
        return (None, None, str(exc))


def _refresh_blocking() -> list[TapeItem]:
    """Synchronous fetch loop. Runs in a thread off the event loop."""
    out: list[TapeItem] = []
    for sym, yf_ticker, unit in _BASKET:
        last, chg, err = _fetch_one(yf_ticker)
        out.append(TapeItem(sym=sym, yf=yf_ticker, last=last, change_pct=chg, unit=unit, error=err))
    return out


async def get_tape(force: bool = False) -> dict[str, Any]:
    """Return current tape (cached). Triggers a refresh if cache is cold/stale.

    Shape:
        {
          "as_of": <epoch_seconds>,
          "stale": bool,            # true while serving stale cache during a refresh
          "items": [
            {"sym": "SPX", "yf": "^GSPC", "last": 5478.34, "change_pct": 0.42, "unit": null, "error": null},
            ...
          ]
        }
    """
    now = time.time()
    cached_items = _cache.get("items")
    cached_ts = float(_cache.get("ts") or 0.0)
    fresh = cached_items is not None and (now - cached_ts) < _CACHE_TTL_S
    if fresh and not force:
        return {
            "as_of": cached_ts,
            "stale": False,
            "items": [asdict(it) for it in cached_items],
        }

    # Try to refresh; if we already have cached items, return them first and
    # populate the cache async in the background. On a cold cache we wait.
    if cached_items is not None and not force:
        # serve stale while we refresh in the background (best-effort)
        asyncio.create_task(_refresh_and_store())
        return {
            "as_of": cached_ts,
            "stale": True,
            "items": [asdict(it) for it in cached_items],
        }

    # cold cache - we must wait
    items = await _refresh_and_store()
    return {
        "as_of": float(_cache.get("ts") or now),
        "stale": False,
        "items": [asdict(it) for it in items],
    }


async def _refresh_and_store() -> list[TapeItem]:
    async with _cache_lock:
        # double-check inside the lock: another waiter may have already refreshed
        now = time.time()
        cached_items = _cache.get("items")
        cached_ts = float(_cache.get("ts") or 0.0)
        if cached_items is not None and (now - cached_ts) < _CACHE_TTL_S:
            return cached_items
        try:
            items = await asyncio.to_thread(_refresh_blocking)
        except Exception as exc:
            logger.warning("market tape refresh failed: %s", exc)
            return _cache.get("items") or []
        _cache["items"] = items
        _cache["ts"] = time.time()
        _cache["stale"] = False
        return items


def reset_cache_for_tests() -> None:
    _cache["items"] = None
    _cache["ts"] = 0.0
    _cache["stale"] = True
