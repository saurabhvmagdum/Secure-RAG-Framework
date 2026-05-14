"""
Dependency Injection
=====================

FastAPI dependency functions for injecting service instances into routes.
All dependencies resolve to on-prem implementations only.
"""

from __future__ import annotations

from app.audit.logger import AuditLogger, FileAuditLogger
from app.security.auth import AuthProvider, get_auth_provider
from app.security.policy import DefaultPolicyEngine, PolicyEngine
from app.security.rbac import DefaultRBACEngine, RBACEngine
from app.verification.confidence import ConfidenceScorer, DefaultConfidenceScorer
from app.verification.router import AnswerRouter, DefaultAnswerRouter


def get_rbac_engine() -> RBACEngine:
    """Get the RBAC engine instance."""
    # TODO: Phase 2 — configure with roles from governed store
    return DefaultRBACEngine()


def get_policy_engine() -> PolicyEngine:
    """Get the policy engine instance."""
    return DefaultPolicyEngine()


def get_audit_logger() -> AuditLogger:
    """Get the audit logger instance."""
    return FileAuditLogger()


def get_confidence_scorer() -> ConfidenceScorer:
    """Get the confidence scorer instance."""
    return DefaultConfidenceScorer()


def get_answer_router() -> AnswerRouter:
    """Get the answer router instance."""
    return DefaultAnswerRouter()
