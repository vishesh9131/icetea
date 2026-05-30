"""
End-to-end harness for the Icetea AI multi-agent system.

What it does
------------
1. POSTs each scenario to /v1/chat (SSE).
2. Parses meta/token/structured/error/done events.
3. Runs the scenarios' Check rules ("judge").
4. Writes a per-run report to Logs/harness/run_<ts>.json + a human-readable
   summary to stdout (and Logs/harness/run_<ts>.md).
5. Returns a non-zero exit code if anything failed.

Run via:
    python -m scripts.harness.run --base http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

# Make sibling imports work when run as a module from repo root.
HERE = Path(__file__).resolve().parent
ASSIGNMENT2 = HERE.parent.parent
sys.path.insert(0, str(ASSIGNMENT2))

from scripts.harness.scenarios import SCENARIOS, Scenario, Check  # noqa: E402


# ---------------------------------------------------------------------------
# SSE parsing
# ---------------------------------------------------------------------------


def _parse_sse_stream(text: str) -> list[dict[str, Any]]:
    """Decode an SSE response body into a list of {event, data} dicts."""
    out: list[dict[str, Any]] = []
    event = "message"
    data_lines: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.rstrip("\r")
        if line == "":
            if data_lines:
                body = "\n".join(data_lines)
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:
                    payload = {"raw": body}
                out.append({"event": event, "data": payload})
            event = "message"
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].lstrip())
    if data_lines:
        body = "\n".join(data_lines)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"raw": body}
        out.append({"event": event, "data": payload})
    return out


# ---------------------------------------------------------------------------
# Run a scenario
# ---------------------------------------------------------------------------


async def run_one(client: httpx.AsyncClient, base: str, sc: Scenario) -> dict[str, Any]:
    session_id = sc.session_override or f"harness-{sc.sid}-{uuid.uuid4().hex[:6]}"
    body = {
        "query": sc.query,
        "session_id": session_id,
        "collaborative": sc.collaborative,
        "user_context": sc.user_context,
    }
    started = time.perf_counter()
    try:
        resp = await client.post(
            f"{base}/v1/chat",
            json=body,
            timeout=httpx.Timeout(180.0, connect=15.0),
        )
        text = resp.text
        status = resp.status_code
    except Exception as exc:
        return {
            "sid": sc.sid,
            "title": sc.title,
            "session_id": session_id,
            "status": "TRANSPORT_ERROR",
            "error": str(exc),
            "elapsed_s": time.perf_counter() - started,
        }

    elapsed = time.perf_counter() - started
    events = _parse_sse_stream(text)

    tokens: list[str] = []
    meta_events: list[dict[str, Any]] = []
    structured: dict[str, Any] | None = None
    error_events: list[dict[str, Any]] = []
    done_event: dict[str, Any] | None = None
    classified_agent: str | None = None
    safety_blocked: bool | None = None
    safety_category: str | None = None

    for ev in events:
        name = ev["event"]
        data = ev["data"]
        if name == "token":
            tokens.append(str(data.get("delta", "")))
        elif name == "meta":
            meta_events.append(data)
            if data.get("stage") == "classified":
                classified_agent = data.get("agent")
            if data.get("stage") == "safety":
                safety_blocked = bool(data.get("blocked"))
                safety_category = data.get("category")
        elif name == "structured":
            structured = data
        elif name == "error":
            error_events.append(data)
        elif name == "done":
            done_event = data
            classified_agent = classified_agent or data.get("agent")
        # ignore unknown events

    narrative = "".join(tokens)
    record = {
        "sid": sc.sid,
        "title": sc.title,
        "session_id": session_id,
        "http_status": status,
        "elapsed_s": elapsed,
        "events_count": len(events),
        "meta_events": meta_events,
        "structured": structured,
        "narrative": narrative,
        "narrative_excerpt": narrative[:600],
        "error_events": error_events,
        "done_event": done_event,
        "classified_agent": classified_agent,
        "safety_blocked": safety_blocked,
        "safety_category": safety_category,
        "tokens_count": len(tokens),
        "collaborative": sc.collaborative,
        "query": sc.query,
    }

    # --- judge ---
    issues = _judge(record, sc.checks)
    record["pass"] = not issues
    record["issues"] = issues
    return record


def _judge(rec: dict[str, Any], chk: Check) -> list[str]:
    issues: list[str] = []
    text_lower = (rec["narrative"] or "").lower()

    if chk.expects_done and rec.get("done_event") is None:
        issues.append("missing done event")

    if chk.no_errors and rec.get("error_events"):
        issues.append(f"unexpected error events: {rec['error_events']}")

    if chk.expect_blocked is not None:
        if bool(rec.get("safety_blocked")) != chk.expect_blocked:
            issues.append(
                f"expected safety_blocked={chk.expect_blocked}, got {rec.get('safety_blocked')}"
            )

    if chk.expect_block_category is not None:
        if rec.get("safety_category") != chk.expect_block_category:
            issues.append(
                f"expected block category={chk.expect_block_category}, got {rec.get('safety_category')}"
            )

    if chk.must_agent and rec.get("classified_agent") not in chk.must_agent:
        # If query was safety-blocked we deliberately wont have a classified agent,
        # which is fine when expect_blocked is True. Only complain otherwise.
        if not rec.get("safety_blocked"):
            issues.append(
                f"agent={rec.get('classified_agent')!r} not in {sorted(chk.must_agent)}"
            )

    if chk.forbid_agent and rec.get("classified_agent") in chk.forbid_agent:
        issues.append(f"agent {rec.get('classified_agent')} was explicitly forbidden")

    if chk.must_text_any:
        if not any(t.lower() in text_lower for t in chk.must_text_any):
            issues.append(
                f"narrative missing any-of {chk.must_text_any}; got excerpt: {rec['narrative_excerpt'][:200]!r}"
            )

    if chk.must_text_all:
        missing = [t for t in chk.must_text_all if t.lower() not in text_lower]
        if missing:
            issues.append(f"narrative missing all-of: {missing}")

    if chk.forbid_text:
        present = [t for t in chk.forbid_text if t.lower() in text_lower]
        if present:
            issues.append(f"narrative contains forbidden text: {present}")

    if chk.must_structured_keys:
        struct = rec.get("structured") or {}
        if not isinstance(struct, dict):
            issues.append("structured payload missing")
        else:
            missing = [k for k in chk.must_structured_keys if k not in _flatten_keys(struct)]
            if missing:
                issues.append(
                    f"structured payload missing keys: {missing}; have: "
                    f"{sorted(_flatten_keys(struct))[:20]}"
                )

    if chk.must_disclaimer:
        struct = rec.get("structured") or {}
        disc_in_struct = isinstance(struct, dict) and any(
            "disclaim" in k.lower() for k in _flatten_keys(struct)
        )
        if "disclaim" not in text_lower and not disc_in_struct:
            issues.append("missing disclaimer in narrative or structured payload")

    if chk.min_tokens and rec.get("tokens_count", 0) < chk.min_tokens:
        # min_tokens guards against the model going silent. Blocked queries are
        # an exception (they intentionally short-circuit with the refusal text).
        if not rec.get("safety_blocked"):
            issues.append(
                f"too few streamed token deltas: {rec.get('tokens_count')} < {chk.min_tokens}"
            )

    if chk.custom:
        try:
            ok, reason = chk.custom(rec)
            if not ok:
                issues.append(f"custom: {reason}")
        except Exception as exc:
            issues.append(f"custom check raised: {exc}")

    return issues


def _flatten_keys(d: Any, prefix: str = "") -> set[str]:
    out: set[str] = set()
    if isinstance(d, dict):
        for k, v in d.items():
            out.add(k)
            out |= _flatten_keys(v, prefix=f"{prefix}{k}.")
    elif isinstance(d, list):
        for x in d:
            out |= _flatten_keys(x, prefix=prefix)
    return out


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.getenv("HARNESS_BASE", "http://127.0.0.1:8000"))
    ap.add_argument("--filter", default=None, help="substring filter on scenario sid")
    ap.add_argument("--concurrency", type=int, default=1,
                    help="how many scenarios in flight. 1 = strictly serial (default; matters for multi-turn).")
    ap.add_argument("--out-dir", default=str(ASSIGNMENT2 / "Logs" / "harness"))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    Path(args.out_dir).mkdir(parents=True, exist_ok=True)

    # Wipe persisted sessions from any previous harness pass so multi-turn
    # scenarios start clean every time. We are conservative and only delete
    # files that start with `harness-`.
    memdir = ASSIGNMENT2 / "Logs" / "memory"
    if memdir.exists():
        for f in memdir.glob("harness-*.json"):
            try:
                f.unlink()
            except OSError:
                pass

    ts = time.strftime("%Y%m%d-%H%M%S")
    json_path = Path(args.out_dir) / f"run_{ts}.json"
    md_path = Path(args.out_dir) / f"run_{ts}.md"

    scenarios = [s for s in SCENARIOS if args.filter is None or args.filter in s.sid]
    print(f"[harness] running {len(scenarios)} / {len(SCENARIOS)} scenarios against {args.base}")

    # Health probe — fail fast if the server isnt up.
    async with httpx.AsyncClient() as probe:
        try:
            r = await probe.get(f"{args.base}/healthz", timeout=10.0)
            print(f"[harness] healthz {r.status_code} {r.text[:160]}")
            if r.status_code != 200:
                print("[harness] FATAL: healthz not OK; bail")
                return 2
        except Exception as exc:
            print(f"[harness] FATAL: healthz failed: {exc}")
            return 2

    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient() as client:
        if args.concurrency <= 1:
            for sc in scenarios:
                rec = await run_one(client, args.base, sc)
                results.append(rec)
                _print_result(rec, quiet=args.quiet)
        else:
            # Multi-turn scenarios share a session_override and MUST run in
            # order, otherwise the carryover/memory checks become flaky. So we
            # group scenarios by session, run each group sequentially as a unit,
            # and parallelise across groups up to args.concurrency.
            sem = asyncio.Semaphore(args.concurrency)
            groups: dict[str, list[Scenario]] = {}
            for sc in scenarios:
                key = sc.session_override or f"__solo__{sc.sid}"
                groups.setdefault(key, []).append(sc)

            print_lock = asyncio.Lock()

            async def _run_group(group_key: str, group: list[Scenario]) -> list[dict[str, Any]]:
                async with sem:
                    out: list[dict[str, Any]] = []
                    for sc in group:
                        rec = await run_one(client, args.base, sc)
                        out.append(rec)
                        # Print under a lock so interleaved lines stay readable.
                        async with print_lock:
                            _print_result(rec, quiet=args.quiet)
                    return out

            grouped_results = await asyncio.gather(
                *[_run_group(k, g) for k, g in groups.items()]
            )
            # Flatten back in the original scenario order so reports match
            # the SCENARIOS list rather than completion order.
            by_sid: dict[str, dict[str, Any]] = {}
            for chunk in grouped_results:
                for rec in chunk:
                    by_sid[rec["sid"]] = rec
            results = [by_sid[sc.sid] for sc in scenarios if sc.sid in by_sid]

    passed = sum(1 for r in results if r.get("pass"))
    failed = len(results) - passed
    summary = {
        "ts": ts,
        "base": args.base,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
    }
    json_path.write_text(json.dumps(summary, indent=2, default=str))

    md_lines = [
        f"# Harness run {ts}",
        "",
        f"- base: `{args.base}`",
        f"- scenarios: **{len(results)}**",
        f"- passed: **{passed}**",
        f"- failed: **{failed}**",
        "",
        "| sid | status | agent | tokens | elapsed | title | issues |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        status = "PASS" if r.get("pass") else "FAIL"
        ag = r.get("classified_agent") or ("BLOCKED" if r.get("safety_blocked") else "-")
        issues = "; ".join(r.get("issues") or []) or "-"
        issues = issues.replace("|", "/")
        md_lines.append(
            f"| {r['sid']} | {status} | {ag} | {r.get('tokens_count', 0)} | "
            f"{r.get('elapsed_s', 0):.1f}s | {r['title']} | {issues} |"
        )
    md_path.write_text("\n".join(md_lines))

    print()
    print(f"[harness] DONE  passed={passed}  failed={failed}  total={len(results)}")
    print(f"[harness] json -> {json_path}")
    print(f"[harness] md   -> {md_path}")
    return 0 if failed == 0 else 1


def _print_result(rec: dict[str, Any], *, quiet: bool) -> None:
    status = "PASS" if rec.get("pass") else "FAIL"
    ag = rec.get("classified_agent") or ("BLOCKED" if rec.get("safety_blocked") else "?")
    msg = (
        f"  [{status}] {rec['sid']:<28} agent={ag:<22} "
        f"tokens={rec.get('tokens_count', 0):<4} "
        f"{rec.get('elapsed_s', 0):>5.1f}s  {rec['title']}"
    )
    print(msg)
    if not rec.get("pass") and not quiet:
        for issue in rec.get("issues") or []:
            print(f"        - {issue}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
