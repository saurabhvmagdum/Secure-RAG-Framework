"""
Health & Readiness Probes
==========================

Provides health and readiness endpoints for infrastructure monitoring.
No authentication required for health probes (used by load balancers / k8s).
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel

from fastapi import APIRouter

from app import __version__

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    timestamp: str
    services: dict[str, str]


class ReadinessResponse(BaseModel):
    """Readiness check response."""

    ready: bool
    checks: dict[str, bool]


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Basic health check — returns UP if the API server is running.",
)
async def health_check() -> HealthResponse:
    """Simple liveness probe — always returns UP if the server is running."""
    return HealthResponse(
        status="UP",
        version=__version__,
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
        services={
            "api": "UP",
            # TODO: Phase 2 — add backend service health checks
            "opensearch": "UNCHECKED",
            "qdrant": "UNCHECKED",
            "neo4j": "UNCHECKED",
            "llm": "UNCHECKED",
        },
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness check",
    description="Checks if all required backend services are available.",
)
async def readiness_check() -> ReadinessResponse:
    """
    Readiness probe for Kubernetes / load balancers.

    Returns ready=True only when all required services are reachable.
    """
    # TODO: Phase 2 — implement actual health checks for each backend
    checks = {
        "api_server": True,
        "opensearch": False,  # Not connected in Phase 1
        "qdrant": False,
        "neo4j": False,
        "llm_model_loaded": False,
    }

    all_ready = all(checks.values())

    return ReadinessResponse(
        ready=all_ready,
        checks=checks,
    )
