"""
Policy Engine
=============

Protocol for classification-aware policy evaluation.
Combines RBAC checks with data classification rules to make
composite allow/deny decisions before any pipeline operation.

Every pipeline stage must call the policy engine before proceeding.
Fail-closed on any error.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.models.auth import Principal
from app.models.metadata import DocumentMetadata

logger = get_logger(__name__)


class PolicyDecision(str, Enum):
    """Policy evaluation outcome."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    DENY_CLASSIFICATION = "DENY_CLASSIFICATION"
    DENY_RBAC = "DENY_RBAC"


class PolicyResult(BaseModel):
    """Structured policy evaluation result."""

    decision: PolicyDecision
    principal_id: str
    action: str
    resource: str
    reason: str = ""
    classification_level: str | None = None
    applied_rules: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


@runtime_checkable
class PolicyEngine(Protocol):
    """
    Protocol for unified policy evaluation.

    Combines RBAC + data classification + domain constraints into a
    single policy decision. Implementations must enforce all governance
    rules from .antigravityrules.
    """

    def evaluate(
        self,
        principal: Principal,
        action: str,
        resource: str,
        metadata: DocumentMetadata | None = None,
        context: dict[str, Any] | None = None,
    ) -> PolicyResult:
        """
        Evaluate whether the principal may perform the action on the resource,
        considering both RBAC and data classification constraints.

        Args:
            principal: Authenticated principal
            action: The action being attempted
            resource: The resource being accessed
            metadata: Document/chunk metadata for classification checks
            context: Additional context (e.g., checkpoint name)

        Returns:
            PolicyResult with decision and applied rules
        """
        ...

    def evaluate_index_write(
        self,
        principal: Principal,
        index_type: str,
        metadata: DocumentMetadata,
    ) -> PolicyResult:
        """
        Specialized check for index write operations.

        Ensures the principal has WRITE_INDEX permission AND the data
        classification allows writing to the specified index type.
        """
        ...

    def evaluate_retrieval(
        self,
        principal: Principal,
        max_sensitivity: str,
        domain_tags: list[str] | None = None,
    ) -> PolicyResult:
        """
        Specialized check for retrieval operations.

        Ensures the principal may query data up to the given sensitivity level
        and within the given domain scope.
        """
        ...


class DefaultPolicyEngine:
    """
    Default policy engine implementation.

    Combines RBAC permission checking with data classification rules.
    Fail-closed: any evaluation error results in DENY.

    TODO: Phase 2 — integrate with ClassificationEngine for full rule evaluation.
    """

    def __init__(self) -> None:
        """Initialize policy engine."""
        # TODO: Phase 2 — inject RBACEngine and ClassificationEngine
        pass

    def evaluate(
        self,
        principal: Principal,
        action: str,
        resource: str,
        metadata: DocumentMetadata | None = None,
        context: dict[str, Any] | None = None,
    ) -> PolicyResult:
        """Evaluate combined policy — fail-closed."""
        try:
            # TODO: Phase 2 — implement full RBAC + classification evaluation
            logger.info(
                "policy_evaluate",
                principal_id=principal.principal_id,
                action=action,
                resource=resource,
                has_metadata=metadata is not None,
            )

            # Phase 1: Stub — DENY by default (fail-closed)
            return PolicyResult(
                decision=PolicyDecision.DENY,
                principal_id=principal.principal_id,
                action=action,
                resource=resource,
                reason="Policy engine not yet configured — fail-closed default",
                applied_rules=["DEFAULT_DENY"],
            )

        except Exception as exc:
            logger.error(
                "policy_evaluation_error",
                principal_id=principal.principal_id,
                action=action,
                resource=resource,
                error=str(exc),
            )
            return PolicyResult(
                decision=PolicyDecision.DENY,
                principal_id=principal.principal_id,
                action=action,
                resource=resource,
                reason=f"Policy evaluation error (fail-closed): {exc}",
            )

    def evaluate_index_write(
        self,
        principal: Principal,
        index_type: str,
        metadata: DocumentMetadata,
    ) -> PolicyResult:
        """Check index write permission — fail-closed stub."""
        return self.evaluate(
            principal=principal,
            action="WRITE_INDEX",
            resource=f"INDEX:{index_type.upper()}",
            metadata=metadata,
            context={"index_type": index_type},
        )

    def evaluate_retrieval(
        self,
        principal: Principal,
        max_sensitivity: str,
        domain_tags: list[str] | None = None,
    ) -> PolicyResult:
        """Check retrieval permission — fail-closed stub."""
        return self.evaluate(
            principal=principal,
            action="RUN_QUERY",
            resource="RAG_PIPELINE",
            context={
                "max_sensitivity": max_sensitivity,
                "domain_tags": domain_tags,
            },
        )
