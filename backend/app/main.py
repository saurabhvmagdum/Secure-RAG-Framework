"""
FastAPI Application Factory
=============================

Creates and configures the FastAPI application with:
- Audit middleware (correlation IDs, request logging)
- Auth middleware (JWT validation)
- CORS (internal origins only)
- Structured logging
- Health and API routes

Zero external network calls. Zero cloud SDK imports.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __app_name__, __version__
from app.api.router import api_router
from app.audit.middleware import AuditMiddleware
from app.config import settings
from app.core.logging import configure_logging, get_logger


def create_app() -> FastAPI:
    """
    Application factory — creates and configures the FastAPI instance.

    Usage:
        uvicorn app.main:create_app --factory --reload
    """
    # Configure structured logging before anything else
    configure_logging(settings.app.app_log_level)
    logger = get_logger(__name__)

    app = FastAPI(
        title="ISRO Secure On-Premise RAG Framework",
        description=(
            "Fully offline Retrieval-Augmented Generation platform. "
            "Returns grounded, verifiable, source-linked answers from "
            "mission-critical knowledge bases."
        ),
        version=__version__,
        docs_url="/docs" if settings.app.app_debug else None,
        redoc_url="/redoc" if settings.app.app_debug else None,
        openapi_url="/openapi.json" if settings.app.app_debug else None,
    )

    # ── Middleware (order matters — last added = first executed) ──────────

    # CORS — restricted to internal origins only
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.app_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID"],
    )

    # Audit middleware — correlation ID + request logging
    app.add_middleware(AuditMiddleware)

    # ── Routes ───────────────────────────────────────────────────────────
    app.include_router(api_router, prefix="/api")

    # ── Startup / Shutdown Events ────────────────────────────────────────

    @app.on_event("startup")
    async def startup_event() -> None:
        logger.info(
            "application_startup",
            app_name=__app_name__,
            version=__version__,
            environment=settings.app.app_env.value,
            debug=settings.app.app_debug,
        )

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        logger.info("application_shutdown")

    return app
