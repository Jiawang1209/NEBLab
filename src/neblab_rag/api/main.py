"""FastAPI application factory.

Use the factory pattern (``create_app``) so importing this module has no
side effects. Run with::

    uvicorn neblab_rag.api.main:create_app --factory --reload --port 8000
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from neblab_rag.api.routes import health
from neblab_rag.api.routes import query as query_routes
from neblab_rag.config import get_settings
from neblab_rag.logging_config import configure_logging

# Sprint 3: Next.js dev server (web/) hits the API directly because Next's
# rewrite proxy buffers Server-Sent Events. Add production frontend origins
# via NEBLAB_CORS_ORIGINS=https://app.example.com,https://other.example.com
DEFAULT_DEV_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def _resolve_cors_origins() -> list[str]:
    extra = os.environ.get("NEBLAB_CORS_ORIGINS", "").strip()
    if not extra:
        return DEFAULT_DEV_ORIGINS
    parsed = [o.strip() for o in extra.split(",") if o.strip()]
    return [*DEFAULT_DEV_ORIGINS, *parsed]


def create_app() -> FastAPI:
    """Build the FastAPI app with config + logging + routers wired in."""
    settings = get_settings()
    configure_logging(level=settings.log_level)

    app = FastAPI(
        title="NEBLab RAG API",
        version="0.1.0",
        description="北方生态屏障数字实验室 RAG 知识库",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_resolve_cors_origins(),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(query_routes.router)
    return app
