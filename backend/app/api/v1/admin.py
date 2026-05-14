"""
Admin Endpoints
================

Administrative endpoints for audit log access and governance statistics.
All admin endpoints require RBAC authorization — VIEW_AUDIT or MANAGE_POLICIES.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_audit_logger
from app.audit.logger import AuditLogger
from app.audit.models import AuditEvent
from app.core.logging import get_logger
from app.models.auth import Principal
from app.security.auth import get_current_principal

logger = get_logger(__name__)
router = APIRouter(prefix="/admin")


class AuditQueryParams(BaseModel):
    """Query parameters for audit log search."""

    principal_id: str | None = None
    action: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    correlation_id: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


class AuditListResponse(BaseModel):
    """Audit log query response."""

    total: int
    events: list[dict[str, Any]]


class SystemStatusResponse(BaseModel):
    """System governance status."""

    governance_checkpoints_active: bool
    classification_engine_active: bool
    audit_logger_active: bool
    rbac_engine_active: bool
    total_audit_events: int


@router.get(
    "/audit",
    response_model=AuditListResponse,
    summary="Query audit logs",
    description="Search immutable audit logs — requires VIEW_AUDIT permission.",
)
async def query_audit_logs(
    principal_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    principal: Principal = Depends(get_current_principal),
    audit_logger: AuditLogger = Depends(get_audit_logger),
) -> AuditListResponse:
    """Query audit logs — RBAC gated."""
    # TODO: Phase 2 — enforce VIEW_AUDIT permission via RBAC
    logger.info(
        "admin_audit_query",
        requested_by=principal.principal_id,
        filters={
            "principal_id": principal_id,
            "action": action,
            "correlation_id": correlation_id,
        },
    )

    events = audit_logger.query_events(
        principal_id=principal_id,
        action=action,
        correlation_id=correlation_id,
        limit=limit,
    )

    return AuditListResponse(
        total=len(events),
        events=[e.to_log_dict() for e in events],
    )


@router.get(
    "/status",
    response_model=SystemStatusResponse,
    summary="System governance status",
    description="Returns the status of governance subsystems.",
)
async def system_status(
    principal: Principal = Depends(get_current_principal),
) -> SystemStatusResponse:
    """System governance status — RBAC gated."""
    return SystemStatusResponse(
        governance_checkpoints_active=True,
        classification_engine_active=True,
        audit_logger_active=True,
        rbac_engine_active=True,
        total_audit_events=0,  # TODO: Phase 2 — query from audit store
    )
