"""Netlify serverless entry — wraps the FastAPI app with Mangum (Lambda ASGI)."""
from __future__ import annotations

import sys
from pathlib import Path

# netlify/functions/server/server.py -> repo root is three levels up
ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from mangum import Mangum  # noqa: E402

from icetea.api.app import app  # noqa: E402

# lifespan off — no uvicorn startup/shutdown hooks in lambda
_handler = Mangum(app, lifespan="off")


def handler(event, context):
    return _handler(event, context)
