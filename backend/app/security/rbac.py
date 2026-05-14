"""
RBAC Engine
===========

Protocol and base implementation for Role-Based Access Control.
The engine evaluates whether a principal has permission to perform
an action on a resource, considering sensitivity and domain constraints.

Fail-closed: any error during evaluation results in DENY.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.models.auth import Permission, PermissionAction, Principal
from app.models.metadata import DomainTag, SensitivityLevel

logger = get_logger(__name__)


class AuthzDecision(str, Enum):
    """Authorization decision outcome."""

    ALLOW = "ALLOW"
    DENY = "DENY"


class AuthzResult(BaseModel):
    """Structured authorization result for audit logging."""

    decision: AuthzDecision
    principal_id: str
    action: str
    resource: str
    reason: str = ""
    matched_permission_id: str | None = None

    model_config = {"extra": "forbid"}


@runtime_checkable
class RBACEngine(Protocol):
    """
    Protocol for RBAC permission evaluation.

    Implementations must:
    - Load roles and permissions from a governed store
    - Evaluate sensitivity and domain constraints
    - Return DENY on any error (fail-closed)
    - Log every evaluation via audit trail
    """

    def check_permission(
        self,
        principal: Principal,
        action: PermissionAction,
        resource: str,
        required_sensitivity: SensitivityLevel | None = None,
        required_domain: DomainTag | None = None,
    ) -> AuthzResult:
        """
        Evaluate whether the principal may perform the action on the resource.

        Args:
            principal: Authenticated principal (user or service)
            action: The action being attempted
            resource: The resource pattern being accessed
            required_sensitivity: Minimum sensitivity level required (optional)
            required_domain: Domain tag being accessed (optional)

        Returns:
            AuthzResult with ALLOW or DENY and reason
        """
        ...

    def get_principal_permissions(
        self,
        principal: Principal,
    ) -> list[Permission]:
        """Resolve all permissions for a principal based on their roles."""
        ...


class DefaultRBACEngine:
    """
    Default RBAC engine implementation.

    Loads roles from configuration. Evaluates permissions against
    sensitivity and domain constraints. Fail-closed on all errors.
    """

    def __init__(self, roles_config: dict[str, list[Permission]] | None = None) -> None:
        """
        Args:
            roles_config: Mapping of role_id → list of Permission objects.
                          TODO: Phase 2 — load from governed store.
        """
        self._roles_config: dict[str, list[Permission]] = roles_config or {}

    def check_permission(
        self,
        principal: Principal,
        action: PermissionAction,
        resource: str,
        required_sensitivity: SensitivityLevel | None = None,
        required_domain: DomainTag | None = None,
    ) -> AuthzResult:
        """Evaluate permission — fail-closed on any error."""
        try:
            permissions = self.get_principal_permissions(principal)

            for perm in permissions:
                if perm.action != action:
                    continue

                # Check resource pattern match
                if not self._resource_matches(perm.resource, resource):
                    continue

                # Check sensitivity constraint
                if required_sensitivity is not None:
                    if required_sensitivity > perm.constraints.max_sensitivity_level:
                        continue

                # Check domain constraint
                if required_domain is not None:
                    if (
                        perm.constraints.allowed_domain_tags
                        and required_domain not in perm.constraints.allowed_domain_tags
                    ):
                        continue

                logger.info(
                    "rbac_allow",
                    principal_id=principal.principal_id,
                    action=action.value,
                    resource=resource,
                    permission_id=perm.permission_id,
                )
                return AuthzResult(
                    decision=AuthzDecision.ALLOW,
                    principal_id=principal.principal_id,
                    action=action.value,
                    resource=resource,
                    reason="Permission granted",
                    matched_permission_id=perm.permission_id,
                )

            # No matching permission found — DENY
            logger.warning(
                "rbac_deny",
                principal_id=principal.principal_id,
                action=action.value,
                resource=resource,
                reason="no_matching_permission",
            )
            return AuthzResult(
                decision=AuthzDecision.DENY,
                principal_id=principal.principal_id,
                action=action.value,
                resource=resource,
                reason="No matching permission found for the requested action",
            )

        except Exception as exc:
            # FAIL-CLOSED: any error during evaluation → DENY
            logger.error(
                "rbac_evaluation_error",
                principal_id=principal.principal_id,
                action=action.value,
                resource=resource,
                error=str(exc),
            )
            return AuthzResult(
                decision=AuthzDecision.DENY,
                principal_id=principal.principal_id,
                action=action.value,
                resource=resource,
                reason=f"RBAC evaluation error (fail-closed): {exc}",
            )

    def get_principal_permissions(
        self,
        principal: Principal,
    ) -> list[Permission]:
        """Resolve all permissions for a principal based on their assigned roles."""
        permissions: list[Permission] = []
        for role_id in principal.roles:
            role_perms = self._roles_config.get(role_id, [])
            permissions.extend(role_perms)
        return permissions

    @staticmethod
    def _resource_matches(pattern: str, resource: str) -> bool:
        """
        Simple resource pattern matching.

        Supports:
        - Exact match: "INDEX:SEMANTIC" matches "INDEX:SEMANTIC"
        - Wildcard suffix: "DOC:*" matches "DOC:report-123"
        - Universal wildcard: "*" matches everything
        """
        if pattern == "*":
            return True
        if pattern.endswith(":*"):
            prefix = pattern[:-1]  # "DOC:"
            return resource.startswith(prefix)
        return pattern == resource
