"""
FastAPI app factory.

`create_app()` is a factory so tests can spin up their own instance with
overridden dependencies (e.g. a test DB) without contending with the
module-level singleton. The bottom of the file calls the factory once
under the canonical name `app`, which `uvicorn src.api.app:app` boots.

Lifespan: `init_db()` at startup, `close_db()` at shutdown. Both are
idempotent so test fixtures can call them too.

In production (Docker), the built React bundle is mounted at `/` so the
same port serves both the UI and the API. In dev (Vite on :5173), the
mount is skipped because `frontend/dist/` doesn't exist — Vite proxies
`/api` to this server instead. ADR 008.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.api.routes import analytics, clients, upload, uploads, violations
from src.core.database import close_db, init_db

API_V1_PREFIX = "/api/v1"

# Repo-relative path to the production frontend bundle. In a Docker build the
# files end up at `/app/frontend/dist`; locally they end up at
# `<repo>/frontend/dist`. The `parent.parent.parent` resolves to the repo
# root both ways.
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    try:
        yield
    finally:
        await close_db()


def create_app() -> FastAPI:
    """Build a FastAPI instance with every router mounted under `/api/v1`."""
    app = FastAPI(
        title="Lumina Capital Transactions Platform",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=_lifespan,
    )
    app.include_router(analytics.router, prefix=API_V1_PREFIX, tags=["analytics"])
    app.include_router(clients.router, prefix=API_V1_PREFIX, tags=["clients"])
    app.include_router(upload.router, prefix=API_V1_PREFIX, tags=["upload"])
    app.include_router(uploads.router, prefix=API_V1_PREFIX, tags=["uploads"])
    app.include_router(violations.router, prefix=API_V1_PREFIX, tags=["violations"])

    # Static-file mount at "/" comes *after* the API routers so it doesn't
    # shadow them. `html=True` serves `index.html` on the bare root path.
    # Conditional so dev mode (no built bundle on disk) doesn't error.
    if FRONTEND_DIST.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=str(FRONTEND_DIST), html=True),
            name="frontend",
        )
    return app


app = create_app()
