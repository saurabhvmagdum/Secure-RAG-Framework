"""
Audit Event Models
==================

Pydantic schema for immutable audit events matching the specification
in docs/data_layer.md. All fields are required for complete audit trail.

Audit events are append-only — no update or delete operations exist.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AuditAction(str, Enum):
    """Auditable actions across the pipeline."""

    RAG_QUERY_SUBMITTED = "RAG_QUERY_SUBMITTED"
    RAG_QUERY_EXECUTED = "RAG_QUERY_EXECUTED"
    RETRIEVAL_COMPLETE = "RETRIEVAL_COMPLETE"
    VERIFICATION_COMPLETE = "VERIFICATION_COMPLETE"
    GENERATION_COMPLETE = "GENERATION_COMPLETE"
    INDEX_WRITE = "INDEX_WRITE"
    AUTH_SUCCESS = "AUTH_SUCCESS"
    AUTH_FAILURE = "AUTH_FAILURE"
    ACCESS_DENIED = "ACCESS_DENIED"
    INGESTION_COMPLETE = "INGESTION_COMPLETE"
    POLICY_EVALUATION = "POLICY_EVALUATION"
    GOVERNANCE_CHECKPOINT = "GOVERNANCE_CHECKPOINT"
    KEY_ROTATION = "KEY_ROTATION"
    ADMIN_ACTION = "ADMIN_ACTION"


class AuditDecision(str, Enum):
    """Outcome of the audited action."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    ERROR = "ERROR"


class AuditQueryContext(BaseModel):
    """Query-specific context for RAG pipeline audit events."""

    text: str = Field(default="", description="Original query text")
    sensitivity_max: str = Field(
        default="",
        description="Maximum sensitivity level requested",
    )

    model_config = {"extra": "forbid"}


class AuditEvidenceContext(BaseModel):
    """Evidence-specific context for retrieval audit events."""

    doc_ids: list[str] = Field(default_factory=list)
    indices_used: list[str] = Field(default_factory=list)
    chunk_count: int = Field(default=0, ge=0)

    model_config = {"extra": "forbid"}


class AuditVerificationContext(BaseModel):
    """Verification-specific context for verification audit events."""

    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    route: str = Field(default="")
    iterations: int = Field(default=0, ge=0)

    model_config = {"extra": "forbid"}


class AuditNetworkContext(BaseModel):
    """Network context for the audit event."""

    client_ip: str = Field(default="", description="Client IP address")
    user_agent: str = Field(default="", description="Client user agent")

    model_config = {"extra": "forbid"}


class AuditEvent(BaseModel):
    """
    Immutable audit event — the canonical record of every significant action.

    Matches the JSON schema defined in docs/data_layer.md.
    Stored in append-only, write-once medium.
    """

    event_id: str = Field(
        ...,
        min_length=1,
        description="Unique audit event identifier (UUID)",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Event timestamp (UTC)",
    )
    principal_id: str = Field(
        ...,
        min_length=1,
        description="ID of the user or service that triggered the action",
    )
    principal_type: str = Field(
        default="USER",
        description='Principal type: "USER" or "SERVICE"',
    )
    action: AuditAction = Field(
        ...,
        description="The audited action",
    )
    resource: str = Field(
        ...,
        description='Resource affected, e.g. "RAG_PIPELINE", "INDEX:SEMANTIC"',
    )
    request_id: str = Field(
        default="",
        description="Primary request/correlation ID",
    )
    correlation_ids: list[str] = Field(
        default_factory=list,
        description="Sub-operation correlation IDs for cross-referencing",
    )
    query: AuditQueryContext | None = Field(
        default=None,
        description="Query context (for RAG query events)",
    )
    evidence: AuditEvidenceContext | None = Field(
        default=None,
        description="Evidence context (for retrieval events)",
    )
    verification: AuditVerificationContext | None = Field(
        default=None,
        description="Verification context (for verification events)",
    )
    network: AuditNetworkContext | None = Field(
        default=None,
        description="Network context",
    )
    decision: AuditDecision = Field(
        default=AuditDecision.ALLOW,
        description="Outcome of the audited action",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured metadata for this event",
    )

    model_config = {"extra": "forbid"}

    def to_log_dict(self) -> dict[str, Any]:
        """Serialize to dict for structured log output."""
        return self.model_dump(mode="json", exclude_none=True)
