"""
Audit Middleware
================

FastAPI middleware that captures request-level audit events.
Every incoming request is logged with correlation ID, principal,
method, path, status, and timing.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.audit.logger import AuditLogger, FileAuditLogger
from app.audit.models import (
    AuditAction,
    AuditDecision,
    AuditEvent,
    AuditNetworkContext,
)
from app.core.correlation import (
    generate_correlation_id,
    get_correlation_id,
    reset_correlation_context,
    set_correlation_id,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware that:
    1. Generates/propagates correlation ID for each request
    2. Logs request start and completion as audit events
    3. Captures timing, status, and client context
    """

    def __init__(self, app: Any, audit_logger: AuditLogger | None = None) -> None:
        super().__init__(app)
        self._audit_logger: AuditLogger = audit_logger or FileAuditLogger()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Generate or extract correlation ID
        correlation_id = request.headers.get(
            "X-Correlation-ID", generate_correlation_id()
        )
        set_correlation_id(correlation_id)

        start_time = time.monotonic()
        status_code = 500  # Default to error — will be overwritten on success

        try:
            response = await call_next(request)
            status_code = response.status_code

            # Inject correlation ID into response headers
            response.headers["X-Correlation-ID"] = correlation_id

            return response

        except Exception:
            status_code = 500
            raise

        finally:
            duration_ms = (time.monotonic() - start_time) * 1000

            # Log the request as an audit event
            try:
                client_ip = ""
                if request.client:
                    client_ip = request.client.host

                event = AuditEvent(
                    event_id=str(uuid.uuid4()),
                    principal_id=getattr(request.state, "principal_id", "anonymous"),
                    principal_type=getattr(request.state, "principal_type", "USER"),
                    action=AuditAction.RAG_QUERY_EXECUTED,
                    resource=f"{request.method} {request.url.path}",
                    request_id=correlation_id,
                    correlation_ids=[],
                    network=AuditNetworkContext(
                        client_ip=client_ip,
                        user_agent=request.headers.get("user-agent", ""),
                    ),
                    decision=(
                        AuditDecision.ALLOW
                        if status_code < 400
                        else AuditDecision.DENY
                    ),
                    metadata={
                        "method": request.method,
                        "path": str(request.url.path),
                        "status_code": status_code,
                        "duration_ms": round(duration_ms, 2),
                    },
                )

                self._audit_logger.log_event(event)

            except Exception as audit_exc:
                # Never let audit logging failure crash the request
                logger.error(
                    "audit_middleware_failed",
                    error=str(audit_exc),
                    correlation_id=correlation_id,
                )

            finally:
                reset_correlation_context()
