"""Netlify serverless entry — FastAPI via Mangum."""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path


def _backend_dir() -> Path:
    # Lambda zip layout varies; walk a few likely roots instead of hard-coding depth.
    here = Path(__file__).resolve().parent
    roots = [
        here,
        here.parent,
        here.parent.parent,
        here.parent.parent.parent,
        Path("/var/task"),
    ]
    seen: set[Path] = set()
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        for base in (root, root / "backend"):
            if (base / "icetea" / "api" / "app.py").is_file():
                return base
            nested = base / "backend"
            if (nested / "icetea" / "api" / "app.py").is_file():
                return nested
    raise ImportError(f"icetea package not found near {here}")


def _load_app():
    backend = _backend_dir()
    p = str(backend)
    if p not in sys.path:
        sys.path.insert(0, p)
    from mangum import Mangum
    from icetea.api.app import app

    return Mangum(app, lifespan="off")


_mangum = None
_load_error: str | None = None


def handler(event, context):
    global _mangum, _load_error
    if _mangum is None and _load_error is None:
        try:
            _mangum = _load_app()
        except Exception:
            _load_error = traceback.format_exc()
    if _load_error is not None:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "server import failed", "detail": _load_error}),
        }
    return _mangum(event, context)
