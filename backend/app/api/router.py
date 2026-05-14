"""
API Router
==========

Central router that assembles all API sub-routers under the /v1 prefix.
"""

from fastapi import APIRouter
from app.api.v1 import health, ingest, query, admin

api_router = APIRouter()

# V1 API group — all endpoints live under /api/v1/...
v1_router = APIRouter(prefix="/v1")
v1_router.include_router(health.router, tags=["health"])
v1_router.include_router(ingest.router, prefix="/ingest", tags=["ingestion"])
v1_router.include_router(query.router, prefix="/query", tags=["query"])
v1_router.include_router(admin.router, tags=["admin"])

api_router.include_router(v1_router)
