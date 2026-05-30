"""
Market research agent.

This is the agent the classifier picks for queries like:
    "how is nvda doing this week?"
    "search the web for the latest on apple's AI strategy"
    "what is the fed up to?"
    "will aapl crash given the siri news"

What it actually does
---------------------
1. Pull the target tickers out of the classifier (entities.tickers); if the
   classifier didnt resolve any, try a cheap symbol-shape scan of the query
   and the user's own portfolio as a last resort.
2. Fetch a live quote + a trailing-21-day return for each ticker via the
   shared market_tools (yfinance backed, TTL-cached so we dont rate-limit).
3. Run 1-3 DuckDuckGo searches: the raw user query, plus per-ticker
   "<TICKER> news this week" queries when we have tickers.
4. Optionally fetch the body of the top 1-2 result URLs through the
   SSRF-filtered web toolkit so the model has actual paragraphs to ground
   on, not just titles + snippets.
5. Stream an analyst-style answer from the LLM, with citations to the URLs
   it leaned on. When no LLM is available we fall back to a deterministic
   list-of-sources answer so the operator still gets something useful.

Output
------
- data events:       streamed narrative
- structured event:  { agent, intent, tickers_analysed, sources,
                       web_queries_used, quotes, return_stats, retrieval_ok }
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, AsyncIterator

from ..config import Settings, get_settings
from ..llm import LLMClient, LLMError, assemble_messages, get_llm_client
from ._streaming import stream_pieces
from ..orchestration.toolkits import market_tools as mkt
from ..orchestration.toolkits import web_tools as wt
from ..safety import MODEL_INJECTION_GUARD


logger = logging.getLogger(__name__)


DISCLAIMER = (
    "Not investment advice. Live quotes can lag; web excerpts may be incomplete. "
    "Verify everything against primary sources before acting."
)


SYSTEM = """You are Icetea's market research analyst.

You have three context blocks you can lean on:
- LIVE_QUOTES: yfinance-backed last price, sector, currency for each ticker.
- RETURN_STATS: trailing 21-day return for each ticker, in percent.
- WEB_CONTEXT: DuckDuckGo headlines (title + url + snippet) and, for the
  top hits, a short plain-text excerpt of the article body.

How to answer:
- Open with one tight paragraph answering the user's question directly.
- Follow with 3-6 bullets that surface the most relevant facts you can
  actually defend from the context blocks. Cite each fact with the URL it
  came from, in parentheses, the first time you use that source.
- Be honest: if the web context is thin or the quote couldnt be fetched,
  say so explicitly instead of inventing numbers.
- Tie it back to the user's portfolio if the ticker is in their book.
- Educational tone. No "buy now" calls; surface drivers + risks instead.
- Keep it under ~350 words.

""" + MODEL_INJECTION_GUARD


# Generic words that look ticker-shaped but are not. Lets us run the symbol
# scan over the raw query without false-positives like "I" or "AI".
_NON_TICKER_WORDS = {
    "A", "I", "AI", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "HI", "IF",
    "IN", "IS", "IT", "ME", "MY", "NO", "OF", "ON", "OR", "SO", "TO", "UP", "US",
    "WE", "ARE", "AND", "ASK", "BUT", "CAN", "FED", "FOR", "GET", "HAS", "HAD",
    "HIM", "HER", "HOW", "ITS", "NEW", "NOT", "NOW", "OUR", "OUT", "SAY", "SEE",
    "SHE", "THE", "TOO", "WAS", "WHO", "WHY", "YES", "YOU", "ANY", "OWN", "ALL",
    "MOST", "WHAT", "WILL", "WITH", "FROM", "HAVE", "THEY", "THAT", "THIS", "THEM",
    "WERE", "ETF", "USA", "CEO", "API", "IPO", "NEWS", "PRICE", "STOCK", "MARKET",
    "WEEK", "MONTH", "YEAR", "SOON", "WHEN", "WHERE", "ALSO", "JUST", "INTO", "OVER",
}


def _scan_query_for_tickers(query: str) -> list[str]:
    """Best-effort ticker scan: 1-5 uppercase letters, optional .EXCH suffix."""
    if not query:
        return []
    out: list[str] = []
    seen: set[str] = set()
    # ^ or word boundary -> 1-5 caps -> optional exchange (.AS / .L / .HK etc)
    for m in re.finditer(r"\b([A-Z]{1,5}(?:\.[A-Z]{1,4})?)\b", query):
        sym = m.group(1)
        base = sym.split(".", 1)[0]
        if base in _NON_TICKER_WORDS:
            continue
        if sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    # Capitalised brand names that arent the ticker (Apple / Nvidia / Microsoft etc).
    # We only attach a few canonical ones - the LLM handles the rest from context.
    BRAND_TO_TICKER = {
        "apple": "AAPL", "nvidia": "NVDA", "microsoft": "MSFT", "tesla": "TSLA",
        "alphabet": "GOOG", "google": "GOOG", "amazon": "AMZN", "meta": "META",
        "facebook": "META", "netflix": "NFLX", "oracle": "ORCL", "intel": "INTC",
        "amd": "AMD", "broadcom": "AVGO", "salesforce": "CRM", "ibm": "IBM",
    }
    qlow = query.lower()
    for brand, tkr in BRAND_TO_TICKER.items():
        if brand in qlow and tkr not in seen:
            seen.add(tkr)
            out.append(tkr)
    return out[:5]


def _resolve_tickers(
    *,
    query: str,
    classification: dict[str, Any],
    user_context: dict[str, Any],
) -> list[str]:
    """Pick the tickers we are going to research."""
    ents = (classification.get("entities") or {})
    raw = ents.get("tickers") or []
    out: list[str] = []
    seen: set[str] = set()
    for t in raw:
        s = str(t or "").strip().upper()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    if out:
        return out[:5]

    # nothing from the classifier - try a scan of the raw query
    scanned = _scan_query_for_tickers(query or "")
    for s in scanned:
        if s not in seen:
            seen.add(s)
            out.append(s)
    if out:
        return out[:5]

    # last resort: borrow the operator's top portfolio name so the user still
    # gets something to chew on for vague "how is the market doing?" prompts
    positions = user_context.get("positions") or []
    if isinstance(positions, list):
        for p in positions[:2]:
            sym = str((p or {}).get("ticker") or "").strip().upper()
            if sym and sym not in seen:
                seen.add(sym)
                out.append(sym)
    return out[:3]


def _build_search_queries(query: str, tickers: list[str]) -> list[str]:
    q = (query or "").strip()
    out: list[str] = []
    if q:
        out.append(q[:400])
    for t in tickers[:3]:
        out.append(f"{t} stock news this week")
    seen: set[str] = set()
    uniq: list[str] = []
    for item in out:
        k = item.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(item)
    return uniq[:4]


def _merge_hits(batches: list[dict[str, Any]]) -> list[dict[str, str]]:
    by_url: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for batch in batches:
        for row in batch.get("results") or []:
            url = (row.get("url") or "").strip()
            if not url.startswith("https://"):
                continue
            if url not in by_url:
                by_url[url] = {
                    "title": (row.get("title") or url).strip(),
                    "url": url,
                    "snippet": (row.get("snippet") or "").strip(),
                }
                order.append(url)
    return [by_url[u] for u in order]


def _format_quotes_block(quotes: list[dict[str, Any]]) -> str:
    if not quotes:
        return "(no live quotes available)"
    lines: list[str] = []
    for q in quotes:
        tkr = q.get("ticker") or "?"
        price = q.get("price")
        cur = q.get("currency") or ""
        name = q.get("name") or ""
        sector = q.get("sector") or ""
        if price is None:
            lines.append(f"- {tkr}: quote unavailable ({q.get('note') or 'no_data'})")
            continue
        lines.append(
            f"- {tkr} ({name or 'n/a'}, {sector or 'n/a'}): {price} {cur}".rstrip()
        )
    return "\n".join(lines)


def _format_returns_block(returns: list[dict[str, Any]]) -> str:
    if not returns:
        return "(no return stats)"
    lines: list[str] = []
    for r in returns:
        tkr = r.get("ticker") or "?"
        pct = r.get("return_pct")
        if pct is None:
            lines.append(f"- {tkr}: trailing return unavailable ({r.get('note') or 'no_data'})")
            continue
        sign = "+" if pct >= 0 else ""
        days = r.get("lookback_days") or 30
        lines.append(f"- {tkr}: {sign}{pct}% over last {days}d")
    return "\n".join(lines)


def _format_web_block(hits: list[dict[str, str]], page_texts: list[tuple[str, str]]) -> str:
    if not hits and not page_texts:
        return "(no web context retrieved)"
    parts: list[str] = []
    for i, h in enumerate(hits[:8], start=1):
        parts.append(
            f"[{i}] {h.get('title')}\nURL: {h.get('url')}\n{h.get('snippet')}".rstrip()
        )
    for url, txt in page_texts:
        parts.append(f"\n--- PAGE {url} ---\n{txt[:3500]}")
    return "\n\n".join(parts)


def _deterministic_answer(
    *,
    query: str,
    tickers: list[str],
    quotes: list[dict[str, Any]],
    returns: list[dict[str, Any]],
    hits: list[dict[str, str]],
) -> str:
    """Fallback when no LLM is configured - we still ship the raw data we pulled."""
    lines: list[str] = []
    if tickers:
        lines.append(f"Market research snapshot for {', '.join(tickers)}:\n")
    else:
        lines.append("Market research snapshot:\n")

    if quotes:
        lines.append("Live quotes:")
        lines.append(_format_quotes_block(quotes))
        lines.append("")
    if returns:
        lines.append("Trailing returns:")
        lines.append(_format_returns_block(returns))
        lines.append("")
    if hits:
        lines.append("Top web sources:")
        for i, h in enumerate(hits[:6], start=1):
            sn = h.get("snippet") or "(no snippet)"
            lines.append(f"{i}. {h.get('title')}")
            lines.append(f"   {sn}")
            lines.append(f"   {h.get('url')}")
        lines.append("")
    if not (quotes or returns or hits):
        lines.append(
            "I couldnt reach yfinance or DuckDuckGo just now - try again in a minute "
            "or check the backend's WEB_FETCH_ENABLED setting."
        )

    lines.append(DISCLAIMER)
    return "\n".join(lines)


def _maybe_llm_client(llm: Any | None) -> LLMClient | None:
    if llm is not None:
        return llm if hasattr(llm, "stream_text") else None
    try:
        c = get_llm_client()
    except Exception:
        return None
    return c if hasattr(c, "stream_text") else None


def _split_stream(text: str, *, chunk_size: int = 40) -> list[str]:
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


class MarketResearchAgent:
    name = "market_research"

    async def run(
        self,
        *,
        query: str,
        user_context: dict[str, Any],
        classification: dict[str, Any],
        llm: Any | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        settings: Settings = get_settings()
        tickers = _resolve_tickers(
            query=query,
            classification=classification,
            user_context=user_context,
        )

        yield {
            "type": "meta",
            "stage": "market_research_start",
            "tickers": tickers,
            "web_fetch_enabled": settings.web_fetch_enabled,
        }

        # ---- live quotes + recent returns (parallel, in a thread) -------
        quotes: list[dict[str, Any]] = []
        returns: list[dict[str, Any]] = []
        if tickers:
            quote_tasks = [
                asyncio.to_thread(mkt.toolkit_get_quote, t) for t in tickers
            ]
            return_tasks = [
                asyncio.to_thread(mkt.toolkit_get_recent_returns, t, 21) for t in tickers
            ]
            try:
                quotes = await asyncio.gather(*quote_tasks)
                returns = await asyncio.gather(*return_tasks)
            except Exception as exc:
                logger.warning("market_research: yfinance batch failed: %s", exc)
                quotes = quotes or []
                returns = returns or []
            yield {
                "type": "meta",
                "stage": "market_data_loaded",
                "quote_count": len(quotes),
                "return_count": len(returns),
            }

        # ---- web search + optional article fetch ------------------------
        web_queries = _build_search_queries(query, tickers)
        batches: list[dict[str, Any]] = []
        for sq in web_queries:
            res = await asyncio.to_thread(wt.toolkit_web_search, sq, settings=settings)
            batches.append(res)
            # bail early if we already have enough material
            if sum(len(b.get("results") or []) for b in batches) >= 8:
                break

        hits = _merge_hits(batches)
        retrieval_ok = len(hits) > 0
        yield {
            "type": "meta",
            "stage": "web_search_done",
            "queries": web_queries,
            "hits": len(hits),
        }

        page_texts: list[tuple[str, str]] = []
        if settings.web_fetch_enabled and hits:
            # fetch the top 2 result bodies in parallel so the model has
            # paragraph-grade context, not just snippets
            top = hits[:2]
            fetched = await asyncio.gather(*[
                asyncio.to_thread(wt.toolkit_fetch_url, h.get("url") or "", settings=settings)
                for h in top
            ])
            for f in fetched:
                if f.get("ok") and (f.get("text") or "").strip():
                    page_texts.append((
                        str(f.get("url") or ""),
                        str(f.get("text") or ""),
                    ))

        # ---- build the LLM prompt --------------------------------------
        ctx_quotes = _format_quotes_block(quotes)
        ctx_returns = _format_returns_block(returns)
        ctx_web = _format_web_block(hits, page_texts)

        hist = list(conversation_history or [])
        if hist and hist[-1].get("role") == "user":
            hist = hist[:-1]

        user_blob = (
            f"USER_QUESTION:\n{query}\n\n"
            f"TICKERS_IN_FOCUS: {', '.join(tickers) if tickers else '(none resolved)'}\n\n"
            f"LIVE_QUOTES:\n{ctx_quotes}\n\n"
            f"RETURN_STATS:\n{ctx_returns}\n\n"
            f"WEB_CONTEXT:\n{ctx_web}\n"
        )

        # ---- stream the answer -----------------------------------------
        narrative = ""
        client = _maybe_llm_client(llm)
        if client is None:
            narrative = _deterministic_answer(
                query=query, tickers=tickers, quotes=quotes,
                returns=returns, hits=hits,
            )
            for chunk in _split_stream(narrative):
                yield {"type": "data", "delta": chunk}
        else:
            messages = assemble_messages(system=SYSTEM, history=hist, user=user_blob)
            had_content = False
            try:
                # bumped from 750 -> 1500 so reasoning models still have
                # enough budget for the actual answer after CoT
                async for channel, piece in stream_pieces(
                    client, messages, temperature=0.3, max_tokens=1500,
                ):
                    if channel == "think":
                        yield {"type": "thinking", "delta": piece}
                        continue
                    had_content = True
                    narrative += piece
                    yield {"type": "data", "delta": piece}
            except LLMError as exc:
                logger.warning("market_research LLM stream failed: %s", exc)
                # leave whatever we already streamed in place; append the
                # deterministic block so the operator still sees the data
                tail = "\n\n" + _deterministic_answer(
                    query=query, tickers=tickers, quotes=quotes,
                    returns=returns, hits=hits,
                )
                narrative += tail
                for chunk in _split_stream(tail):
                    yield {"type": "data", "delta": chunk}
                had_content = True
            if not had_content:
                fallback = _deterministic_answer(
                    query=query, tickers=tickers, quotes=quotes,
                    returns=returns, hits=hits,
                )
                narrative += fallback
                for chunk in _split_stream(fallback):
                    yield {"type": "data", "delta": chunk}

        sources = [{"title": h.get("title"), "url": h.get("url")} for h in hits[:12]]
        yield {
            "type": "structured",
            "payload": {
                "agent": self.name,
                "implemented": True,
                "intent": classification.get("intent"),
                "entities": classification.get("entities") or {},
                "tickers_analysed": tickers,
                "quotes": quotes,
                "return_stats": returns,
                "web_queries_used": web_queries,
                "sources": sources,
                "web_retrieval_ok": retrieval_ok,
                "fetched_pages": [u for (u, _t) in page_texts],
                "message": narrative.strip(),
                "disclaimer": DISCLAIMER,
            },
        }
