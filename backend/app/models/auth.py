"""
Authentication & Authorization Schemas
=======================================

RBAC model: Principal → Role → Permission.
Designed for JWT-based internal auth (Phase 1) with an LDAP/AD-compatible
abstraction for future migration.

Permissions are constrained by sensitivity level and domain tags.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.models.metadata import DomainTag, SensitivityLevel


class PrincipalType(str, Enum):
    """Type of authenticated principal."""

    USER = "USER"
    SERVICE = "SERVICE"


class PermissionAction(str, Enum):
    """Permitted actions in the RBAC system."""

    READ_DOC = "READ_DOC"
    WRITE_INDEX = "WRITE_INDEX"
    RUN_QUERY = "RUN_QUERY"
    VIEW_AUDIT = "VIEW_AUDIT"
    MANAGE_USERS = "MANAGE_USERS"
    MANAGE_POLICIES = "MANAGE_POLICIES"
    INGEST_DOCUMENTS = "INGEST_DOCUMENTS"


class PermissionConstraints(BaseModel):
    """
    Constraints on a permission — limits what subset of data
    the permission applies to based on sensitivity and domain.
    """

    max_sensitivity_level: SensitivityLevel = Field(
        default=SensitivityLevel.INTERNAL,
        description="Maximum sensitivity level the principal may access",
    )
    allowed_domain_tags: list[DomainTag] = Field(
        default_factory=lambda: list(DomainTag),
        description="Domain tags the principal may access (empty = all)",
    )

    model_config = {"extra": "forbid"}


class Permission(BaseModel):
    """
    A single permission granting a specific action on a resource pattern,
    subject to sensitivity and domain constraints.
    """

    permission_id: str = Field(
        ...,
        min_length=1,
        description="Unique permission identifier",
    )
    action: PermissionAction = Field(
        ...,
        description="Action this permission grants",
    )
    resource: str = Field(
        ...,
        min_length=1,
        description='Resource pattern, e.g. "DOC:*", "INDEX:SEMANTIC", "GRAPH:*"',
    )
    constraints: PermissionConstraints = Field(
        default_factory=PermissionConstraints,
        description="Sensitivity and domain access constraints",
    )

    model_config = {"extra": "forbid"}


class Role(BaseModel):
    """
    A named role containing a set of permissions.

    Standard roles: RAG_USER, RAG_ANALYST, RAG_ADMIN, RAG_AUDITOR
    """

    role_id: str = Field(
        ...,
        min_length=1,
        description="Unique role identifier",
    )
    name: str = Field(
        ...,
        min_length=1,
        description='Human-readable role name, e.g. "RAG User"',
    )
    description: str = Field(
        default="",
        description="Role description",
    )
    permissions: list[Permission] = Field(
        default_factory=list,
        description="Permissions granted by this role",
    )

    model_config = {"extra": "forbid"}


class Principal(BaseModel):
    """
    An authenticated principal — either a user or a service.

    The principal is extracted from JWT tokens by the auth middleware
    and attached to the request context for RBAC evaluation.
    """

    principal_id: str = Field(
        ...,
        min_length=1,
        description="Unique user or service identifier",
    )
    type: PrincipalType = Field(
        ...,
        description="Whether this is a user or service principal",
    )
    display_name: str = Field(
        default="",
        description="Human-readable display name",
    )
    roles: list[str] = Field(
        default_factory=list,
        description='Role IDs assigned, e.g. ["RAG_USER", "RAG_ADMIN"]',
    )

    model_config = {"extra": "forbid"}
