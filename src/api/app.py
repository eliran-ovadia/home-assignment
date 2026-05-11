"""
FastAPI app factory.

`create_app()` is a factory so tests can spin up their own instance with
overridden dependencies (e.g. a test DB) without contending with the
module-level singleton. The bottom of the file calls the factory once
under the canonical name `app`, which `uvicorn src.api.app:app` boots.

Lifespan: `init_db()` at startup, `close_db()` at shutdown. Both are
idempotent so test fixtures can call them too.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.routes import analytics, clients, upload, uploads, violations
from src.core.database import close_db, init_db

API_V1_PREFIX = "/api/v1"


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
    app.include_router(upload.router, prefix=API_V1_PREFIX, tags=["upload"])
    app.include_router(clients.router, prefix=API_V1_PREFIX, tags=["clients"])
    app.include_router(violations.router, prefix=API_V1_PREFIX, tags=["violations"])
    app.include_router(analytics.router, prefix=API_V1_PREFIX, tags=["analytics"])
    app.include_router(uploads.router, prefix=API_V1_PREFIX, tags=["uploads"])
    return app


app = create_app()
