"""Web fetch + lightweight search — shared by ProductRecommendationAgent and MCP web_server."""
from __future__ import annotations

import html as html_module
import ipaddress
import logging
import re
import socket
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse, urljoin

import httpx

from ...config import Settings, get_settings

logger = logging.getLogger(__name__)

_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_MAX_REDIRECTS = 5
_BODY_READ_CHUNK = 65536


def _strip_tags(blob: str, max_chars: int) -> str:
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", blob)
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html_module.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:max_chars]


# Tags that almost always wrap site chrome, not article text. Stripping them
# whole avoids the "Skip to navigation, Skip to main content, US Politics,
# World, Weather..." pollution we get from naive tag-stripping news pages.
_CHROME_TAGS = ("script", "style", "nav", "header", "footer", "aside", "form",
                "button", "noscript", "svg", "iframe", "figure")


def _paragraphs_from_p_tags(html: str, min_para_len: int = 80) -> list[str]:
    """Pull paragraph text from <p> tags. This is the highest-signal extraction
    technique for news sites - nav menus use <a>/<li>, body content uses <p>.
    """
    out: list[str] = []
    for m in re.finditer(r"(?is)<p\b[^>]*>(.*?)</p>", html):
        inner = m.group(1)
        # strip inline tags
        text = re.sub(r"(?s)<[^>]+>", " ", inner)
        text = html_module.unescape(text)
        text = re.sub(r"[ \t\u00a0]+", " ", text).strip()
        # discard short paragraphs (captions, taglines) AND boilerplate
        if len(text) < min_para_len:
            continue
        lower = text.lower()
        if any(b in lower for b in (
            "cookie policy", "privacy policy", "terms of service",
            "subscribe to our newsletter", "all rights reserved",
            "use of this site constitutes",
        )):
            continue
        out.append(text)
    return out


def extract_article_text(html: str, max_chars: int) -> str:
    """Best-effort readability pass — returns article text with paragraph breaks.

    Strategy (cheap, no third-party deps):
      1. Try to pull paragraph text from <p> tags directly (highest signal:
         nav menus use <a>/<li>, body content uses <p>). If we get >= 3 real
         paragraphs we are done.
      2. Otherwise fall back to: strip chrome containers (nav/header/footer/...),
         prefer <article>/<main>, convert block tags to newlines, then keep
         only lines that look like prose (long, sentence-ending punctuation).

    Not a perfect Mozilla-Readability extraction but dramatically better than
    naive strip-tags for Yahoo Finance / Motley Fool / Reuters / Barron's.
    """
    if not html:
        return ""

    # ---- preferred path: extract from <p> tags ----
    paragraphs = _paragraphs_from_p_tags(html)
    if len(paragraphs) >= 3:
        joined = "\n\n".join(paragraphs)
        return joined[:max_chars]

    # 1. drop chrome wholesale
    h = html
    for tag in _CHROME_TAGS:
        h = re.sub(
            rf"(?is)<{tag}\b[^>]*>.*?</{tag}\s*>",
            " ",
            h,
        )
    # also drop comments + DOCTYPE
    h = re.sub(r"(?s)<!--.*?-->", " ", h)
    h = re.sub(r"(?i)<!doctype[^>]*>", " ", h)

    # 2. pick a candidate region: <article>...</article> wins, then <main>, then body
    def _first_match(tag: str) -> str | None:
        m = re.search(rf"(?is)<{tag}\b[^>]*>(.*?)</{tag}\s*>", h)
        return m.group(1) if m else None

    candidate = _first_match("article") or _first_match("main") or h

    # 3. convert structural tags to newline markers BEFORE stripping
    candidate = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", candidate)
    candidate = re.sub(
        r"(?is)<\s*(p|h[1-3]|li|tr|blockquote|pre|div)\b[^>]*>",
        "\n",
        candidate,
    )
    candidate = re.sub(
        r"(?is)</\s*(p|h[1-3]|li|tr|blockquote|pre|div)\s*>",
        "\n",
        candidate,
    )

    # 4. strip remaining tags + decode entities
    candidate = re.sub(r"(?s)<[^>]+>", " ", candidate)
    candidate = html_module.unescape(candidate)

    # tidy: collapse runs of spaces within a line, trim each line, drop blanks
    lines = []
    seen_blank = False
    for raw_line in candidate.splitlines():
        line = re.sub(r"[ \t\u00a0]+", " ", raw_line).strip()
        if not line:
            if not seen_blank and lines:
                lines.append("")
                seen_blank = True
            continue
        if len(line) < 3:
            continue
        lines.append(line)
        seen_blank = False

    # Post-filter: drop lines that look like nav crumbs vs real prose.
    # A real article paragraph almost always has either (a) >= 12 words
    # or (b) >= 4 words AND sentence-ending punctuation. Anything else is
    # almost certainly menu/breadcrumb/footer junk. We keep the FIRST line
    # unconditionally because it is usually the article title.
    pruned: list[str] = []
    for i, line in enumerate(lines):
        if line == "":
            if pruned and pruned[-1]:
                pruned.append("")
            continue
        if i == 0:
            pruned.append(line)
            continue
        words = line.split()
        word_count = len(words)
        has_sentence_end = any(c in line for c in ".!?\u2026")
        is_prose = word_count >= 12 or (word_count >= 4 and has_sentence_end) or len(line) > 90
        if is_prose:
            pruned.append(line)

    # tidy trailing blanks
    while pruned and pruned[-1] == "":
        pruned.pop()

    text = "\n".join(pruned).strip()
    return text[:max_chars]


def _dns_host_allowed(hostname: str) -> tuple[bool, str | None]:
    """Reject hosts that resolve only to non-global IPs (SSRF guard)."""
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        return False, f"dns_failed:{exc}"

    seen: set[str] = set()
    for info in infos:
        ip_str = info[4][0]
        if ip_str in seen:
            continue
        seen.add(ip_str)
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if not ip.is_global:
            return False, f"blocked_ip:{ip_str}"
    if not seen:
        return False, "no_addresses"
    return True, None


def _validate_https_url(url: str, settings: Settings) -> tuple[str | None, str | None]:
    """Returns (error_code, detail) or (None, normalized_url)."""
    raw = (url or "").strip()
    if not raw:
        return "empty_url", None
    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https":
        return "https_only", None
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return "missing_host", None

    deny = [x.strip().lower() for x in (settings.web_fetch_host_denylist or "").split(",") if x.strip()]
    allow = [x.strip().lower() for x in (settings.web_fetch_host_allowlist or "").split(",") if x.strip()]
    if allow and not any(host == a or host.endswith("." + a) for a in allow):
        return "host_not_allowlisted", host
    if deny and any(host == d or host.endswith("." + d) for d in deny):
        return "host_denied", host

    ok, why = _dns_host_allowed(host)
    if not ok:
        return "dns_policy", why
    return None, raw


def _unwrap_ddg_redirect(href: str) -> str:
    """DDG wraps outbound links; pull uddg= target when present."""
    try:
        u = urlparse(href)
        if "duckduckgo.com" in (u.netloc or "").lower() and u.path.startswith("/l/"):
            qs = parse_qs(u.query)
            inner = (qs.get("uddg") or [None])[0]
            if inner:
                return unquote(inner)
    except Exception:
        pass
    return href


def _http_timeout(s: Settings) -> httpx.Timeout:
    """Separate connect vs read so TLS handshakes dont stall the whole slot."""
    conn = float(s.web_fetch_connect_timeout_s)
    read = float(s.web_fetch_timeout_s)
    return httpx.Timeout(connect=conn, read=read, write=min(read, 30.0), pool=5.0)


def _parse_ddg_html_results(body: str, mr: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for m in re.finditer(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        body,
        re.IGNORECASE | re.DOTALL,
    ):
        href = html_module.unescape(m.group(1).strip())
        title = _strip_tags(m.group(2), 240)
        url = _unwrap_ddg_redirect(href)
        if not url.startswith("https://"):
            continue
        results.append({"title": title or url, "url": url, "snippet": ""})
        if len(results) >= mr:
            break
    snippets = re.findall(
        r'class="result__snippet"[^>]*>(.*?)</',
        body,
        re.IGNORECASE | re.DOTALL,
    )
    for i, sn in enumerate(snippets):
        if i < len(results):
            results[i]["snippet"] = _strip_tags(sn, 400)
    return results


def _parse_lite_ddg_results(body: str, mr: int) -> list[dict[str, str]]:
    """lite.duckduckgo.com uses different HTML — outbound links still wrap uddg=."""
    results: list[dict[str, str]] = []
    pat = re.compile(
        r'href="(?:https?:)?//duckduckgo\.com/l/\?uddg=([^"&]+)"[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for m in pat.finditer(body):
        if len(results) >= mr:
            break
        raw_u = unquote(html_module.unescape(m.group(1).strip()))
        title = _strip_tags(m.group(2), 240)
        if not raw_u.startswith("https://"):
            continue
        results.append({"title": title or raw_u, "url": raw_u, "snippet": ""})
    return results


def _finalize_search(results: list[dict[str, str]], *, http_status: int | None, phase: str) -> dict[str, Any]:
    """ok only when we actually parsed links — avoids ok=true with empty sources."""
    if results:
        return {"ok": True, "results": results, "note": None}
    note = "no_hits"
    if http_status is not None and http_status != 200:
        note = f"http_status_{http_status}"
    elif phase:
        note = f"no_hits_{phase}"
    return {"ok": False, "results": [], "note": note}


def toolkit_web_search(
    query: str,
    *,
    max_results: int | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Best-effort DuckDuckGo HTML scrape. Returns {ok, results: [{title, url, snippet}], note}."""
    s = settings or get_settings()
    mr = max_results if max_results is not None else s.web_search_max_results
    mr = max(1, min(int(mr), 10))

    if not s.web_fetch_enabled:
        return {"ok": False, "results": [], "note": "web_fetch_disabled"}

    q = (query or "").strip()
    if len(q) < 2:
        return {"ok": False, "results": [], "note": "empty_query"}

    target = "https://html.duckduckgo.com/html/"
    err, _ = _validate_https_url(target, s)
    if err:
        return {"ok": False, "results": [], "note": err}

    headers = {"User-Agent": (s.web_fetch_user_agent or _DEFAULT_UA).strip() or _DEFAULT_UA}
    timeout = _http_timeout(s)
    results: list[dict[str, str]] = []
    last_status: int | None = None

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.post(target, data={"q": q})
            last_status = resp.status_code
            # 202 / non-200 usually means bot wall or empty shell — HTML parser would yield nothing.
            if resp.status_code == 200:
                results = _parse_ddg_html_results(resp.text, mr)

            if not results:
                lite_target = f"https://lite.duckduckgo.com/lite/?q={quote_plus(q)}"
                err_lite, lite_norm = _validate_https_url(lite_target, s)
                if not err_lite:
                    r2 = client.get(lite_norm)
                    last_status = r2.status_code
                    if r2.status_code == 200:
                        extra = _parse_lite_ddg_results(r2.text, mr)
                        seen = {x["url"] for x in results}
                        for row in extra:
                            if row["url"] not in seen:
                                seen.add(row["url"])
                                results.append(row)
                            if len(results) >= mr:
                                break
    except Exception as exc:
        logger.warning("web_search failed: %s", exc)
        return {"ok": False, "results": [], "note": f"request_error:{exc}"}

    return _finalize_search(results[:mr], http_status=last_status, phase="ddg")


def toolkit_fetch_url(
    url: str,
    *,
    max_chars: int | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """HTTPS GET with redirect validation and plain-text extraction."""
    s = settings or get_settings()
    mc = max_chars if max_chars is not None else s.web_fetch_max_chars

    if not s.web_fetch_enabled:
        return {"ok": False, "url": url, "text": "", "note": "web_fetch_disabled"}

    err, normalized = _validate_https_url(url, s)
    if err:
        return {"ok": False, "url": url, "text": "", "note": err}

    headers = {"User-Agent": (s.web_fetch_user_agent or _DEFAULT_UA).strip() or _DEFAULT_UA}
    timeout = _http_timeout(s)
    max_bytes = int(s.web_fetch_max_bytes)

    try:
        with httpx.Client(timeout=timeout, follow_redirects=False, headers=headers) as client:
            current = normalized
            for _ in range(_MAX_REDIRECTS + 1):
                err2, cur_norm = _validate_https_url(current, s)
                if err2:
                    return {"ok": False, "url": url, "text": "", "note": err2}
                resp = client.get(cur_norm)
                if resp.status_code in (301, 302, 303, 307, 308):
                    loc = resp.headers.get("location")
                    if not loc:
                        return {"ok": False, "url": url, "text": "", "note": "redirect_no_location"}
                    current = urljoin(cur_norm, loc)
                    continue
                resp.raise_for_status()
                raw_chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes(_BODY_READ_CHUNK):
                    raw_chunks.append(chunk)
                    total += len(chunk)
                    if total >= max_bytes:
                        break
                raw = b"".join(raw_chunks)
                try:
                    text_blob = raw.decode(resp.encoding or "utf-8", errors="replace")
                except Exception:
                    text_blob = raw.decode("utf-8", errors="replace")
                plain = _strip_tags(text_blob, mc)
                return {"ok": True, "url": cur_norm, "text": plain, "note": None}
    except Exception as exc:
        logger.warning("fetch_url failed: %s", exc)
        return {"ok": False, "url": url, "text": "", "note": f"request_error:{exc}"}


def toolkit_fetch_article(
    url: str,
    *,
    max_chars: int | None = None,
    max_bytes: int | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Like toolkit_fetch_url but applies a smarter article extractor.

    Used by the in-app READER dock tile so users see the article body with
    paragraph structure instead of a single blob mashed together with nav
    menu items.

    Note: news sites like Yahoo Finance ship ~2 MB of HTML/JSON for a single
    article (most of it is sidebar/related/trackers). The default 512 KB
    byte cap from ``web_fetch_max_bytes`` truncates BEFORE the article body
    appears in the document, which is why the reader uses a larger default
    of 4 MB. The text cap is still honoured for what we return to the UI.
    """
    s = settings or get_settings()
    mc = max_chars if max_chars is not None else s.web_fetch_max_chars

    if not s.web_fetch_enabled:
        return {"ok": False, "url": url, "text": "", "note": "web_fetch_disabled"}

    err, normalized = _validate_https_url(url, s)
    if err:
        return {"ok": False, "url": url, "text": "", "note": err}

    headers = {"User-Agent": (s.web_fetch_user_agent or _DEFAULT_UA).strip() or _DEFAULT_UA}
    timeout = _http_timeout(s)
    # 4 MB is enough for every news site I've tested (Yahoo, Motley Fool,
    # Reuters, Barron's, CNBC) and still bounds memory per request.
    mb_cap = max(int(s.web_fetch_max_bytes), 4_194_304)
    if max_bytes is not None:
        mb_cap = int(max_bytes)

    try:
        with httpx.Client(timeout=timeout, follow_redirects=False, headers=headers) as client:
            current = normalized
            for _ in range(_MAX_REDIRECTS + 1):
                err2, cur_norm = _validate_https_url(current, s)
                if err2:
                    return {"ok": False, "url": url, "text": "", "note": err2}
                resp = client.get(cur_norm)
                if resp.status_code in (301, 302, 303, 307, 308):
                    loc = resp.headers.get("location")
                    if not loc:
                        return {"ok": False, "url": url, "text": "", "note": "redirect_no_location"}
                    current = urljoin(cur_norm, loc)
                    continue
                resp.raise_for_status()
                raw_chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes(_BODY_READ_CHUNK):
                    raw_chunks.append(chunk)
                    total += len(chunk)
                    if total >= mb_cap:
                        break
                raw = b"".join(raw_chunks)
                try:
                    text_blob = raw.decode(resp.encoding or "utf-8", errors="replace")
                except Exception:
                    text_blob = raw.decode("utf-8", errors="replace")
                title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", text_blob)
                page_title = html_module.unescape(title_match.group(1).strip()) if title_match else None
                article_text = extract_article_text(text_blob, mc)
                if len(article_text) < 200:
                    article_text = _strip_tags(text_blob, mc)
                return {
                    "ok": True,
                    "url": cur_norm,
                    "text": article_text,
                    "title": page_title,
                    "http_status": resp.status_code,
                    "note": None,
                }
    except Exception as exc:
        logger.warning("fetch_article failed: %s", exc)
        return {"ok": False, "url": url, "text": "", "note": f"request_error:{exc}"}

    return {"ok": False, "url": url, "text": "", "note": "too_many_redirects"}
