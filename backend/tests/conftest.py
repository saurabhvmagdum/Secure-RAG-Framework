"""
Test Configuration
===================

Shared fixtures for the test suite.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.auth import (
    Permission,
    PermissionAction,
    PermissionConstraints,
    Principal,
    PrincipalType,
)
from app.models.metadata import DocumentMetadata, DomainTag, SensitivityLevel


@pytest.fixture
def sample_metadata() -> DocumentMetadata:
    """Sample governed metadata for testing."""
    return DocumentMetadata(
        domain_tag=DomainTag.PROPULSION,
        sensitivity_level=SensitivityLevel.INTERNAL,
        version="1.0.0",
        origin="EDMS/propulsion/docs",
    )


@pytest.fixture
def sample_principal() -> Principal:
    """Sample authenticated user principal."""
    return Principal(
        principal_id="user-001",
        type=PrincipalType.USER,
        display_name="Test User",
        roles=["RAG_USER"],
    )


@pytest.fixture
def admin_principal() -> Principal:
    """Sample admin principal."""
    return Principal(
        principal_id="admin-001",
        type=PrincipalType.USER,
        display_name="Admin User",
        roles=["RAG_ADMIN"],
    )


@pytest.fixture
def sample_permission() -> Permission:
    """Sample READ_DOC permission."""
    return Permission(
        permission_id="perm-read-doc",
        action=PermissionAction.READ_DOC,
        resource="DOC:*",
        constraints=PermissionConstraints(
            max_sensitivity_level=SensitivityLevel.CONFIDENTIAL,
            allowed_domain_tags=[DomainTag.PROPULSION, DomainTag.AVIONICS],
        ),
    )


@pytest.fixture
def correlation_id() -> str:
    """Sample correlation ID."""
    return str(uuid.uuid4())
