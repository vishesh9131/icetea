"""FastAPI app factory."""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import get_settings
from .routes import router


def _allowed_origins() -> list[str]:
    """CORS origins for the browser terminal.

    Defaults cover the Vite dev server on common ports. Overridable from env
    so production deploys can lock it down — comma-separated list, or "*" to
    open it wide (only use that for local hacking).
    """
    raw = os.environ.get("ALLOWED_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=logging.INFO if settings.app_env != "test" else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    app = FastAPI(
        title="Icetea AI",
        version="0.1.0",
        description="AI co-investor microservice — safety, intent, routing, streaming.",
    )
    origins = _allowed_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins if origins != ["*"] else ["*"],
        allow_credentials=False,  # SSE doesnt need cookies for our setup
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Content-Type"],
    )
    app.include_router(router)

    # Hot-load any custom agents the operator created via the builder UI.
    # We defer the import to keep create_app cheap when only routes are needed
    # (the agent registry pulls in the orchestration graph).
    try:
        from ..agents import custom as _custom

        n = _custom.register_all_into_agent_registry()
        if n:
            logging.getLogger(__name__).info("Registered %d custom agent(s) from disk", n)
    except Exception as exc:
        logging.getLogger(__name__).warning("custom agents bootstrap failed: %s", exc)

    return app


app = create_app()
