"""
Exception Hierarchy
===================

All exceptions are fail-closed by design. No security, governance, or evidence
integrity failure is silently swallowed. Every exception carries structured context
for audit logging.

Hierarchy:
    ISRORAGBaseError
    ├── SecurityError
    │   ├── AuthenticationError
    │   ├── AuthorizationError
    │   └── EncryptionError
    ├── GovernanceError
    │   ├── PolicyViolationError
    │   ├── ClassificationError
    │   ├── VocabularyViolationError
    │   └── MetadataSchemaViolationError
    ├── PipelineError
    │   ├── IngestionError
    │   ├── IndexingError
    │   ├── RetrievalError
    │   ├── VerificationError
    │   └── GenerationError
    ├── EvidenceInsufficiencyError
    ├── CircuitBreakerOpenError
    └── StorageError
"""

from __future__ import annotations

from typing import Any


class ISRORAGBaseError(Exception):
    """
    Base exception for all framework errors.

    All exceptions carry:
    - message: Human-readable error description
    - error_code: Machine-readable error code for audit
    - context: Structured metadata for logging
    - correlation_id: Optional correlation ID for tracing
    """

    def __init__(
        self,
        message: str,
        error_code: str = "ISRO_RAG_ERROR",
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = context or {}
        self.correlation_id = correlation_id

    def to_audit_dict(self) -> dict[str, Any]:
        """Serialize exception for audit logging."""
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "context": self.context,
            "correlation_id": self.correlation_id,
        }


# ── Security Errors ─────────────────────────────────────────────────────────


class SecurityError(ISRORAGBaseError):
    """Base for all security-related failures. Always fail-closed."""

    def __init__(
        self,
        message: str,
        error_code: str = "SECURITY_ERROR",
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(message, error_code, context, correlation_id)


class AuthenticationError(SecurityError):
    """Authentication failure — invalid or missing credentials."""

    def __init__(
        self,
        message: str = "Authentication failed",
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(message, "AUTH_FAILURE", context, correlation_id)


class AuthorizationError(SecurityError):
    """Authorization failure — insufficient permissions for the requested action."""

    def __init__(
        self,
        message: str = "Access denied",
        principal_id: str | None = None,
        action: str | None = None,
        resource: str | None = None,
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        ctx = {
            **(context or {}),
            "principal_id": principal_id,
            "action": action,
            "resource": resource,
        }
        super().__init__(message, "AUTHZ_DENIED", ctx, correlation_id)


class EncryptionError(SecurityError):
    """Encryption or decryption operation failure."""

    def __init__(
        self,
        message: str = "Encryption operation failed",
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(message, "ENCRYPTION_ERROR", context, correlation_id)


# ── Governance Errors ───────────────────────────────────────────────────────


class GovernanceError(ISRORAGBaseError):
    """Base for all governance-related failures. Always fail-closed."""

    def __init__(
        self,
        message: str,
        error_code: str = "GOVERNANCE_ERROR",
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(message, error_code, context, correlation_id)


class PolicyViolationError(GovernanceError):
    """A governance policy was violated."""

    def __init__(
        self,
        message: str = "Policy violation",
        policy_name: str | None = None,
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        ctx = {**(context or {}), "policy_name": policy_name}
        super().__init__(message, "POLICY_VIOLATION", ctx, correlation_id)


class ClassificationError(GovernanceError):
    """Data classification rule failure."""

    def __init__(
        self,
        message: str = "Classification check failed",
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(message, "CLASSIFICATION_ERROR", context, correlation_id)


class VocabularyViolationError(GovernanceError):
    """A value was not found in the controlled vocabulary registry."""

    def __init__(
        self,
        field_name: str,
        invalid_value: str,
        allowed_values: list[str] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        msg = f"Vocabulary violation: '{invalid_value}' is not a valid {field_name}"
        ctx: dict[str, Any] = {
            "field_name": field_name,
            "invalid_value": invalid_value,
        }
        if allowed_values is not None:
            ctx["allowed_values"] = allowed_values
        super().__init__(msg, "VOCABULARY_VIOLATION", ctx, correlation_id)


class MetadataSchemaViolationError(GovernanceError):
    """Metadata contains unauthorized fields or missing required fields."""

    def __init__(
        self,
        message: str = "Metadata schema violation",
        unauthorized_fields: list[str] | None = None,
        missing_fields: list[str] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        ctx: dict[str, Any] = {}
        if unauthorized_fields:
            ctx["unauthorized_fields"] = unauthorized_fields
        if missing_fields:
            ctx["missing_fields"] = missing_fields
        super().__init__(message, "METADATA_SCHEMA_VIOLATION", ctx, correlation_id)


# ── Pipeline Errors ─────────────────────────────────────────────────────────


class PipelineError(ISRORAGBaseError):
    """Base for pipeline stage failures."""

    def __init__(
        self,
        message: str,
        error_code: str = "PIPELINE_ERROR",
        stage: str | None = None,
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        ctx = {**(context or {}), "stage": stage}
        super().__init__(message, error_code, ctx, correlation_id)


class IngestionError(PipelineError):
    """Failure during document ingestion."""

    def __init__(
        self,
        message: str = "Ingestion failed",
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(message, "INGESTION_ERROR", "ingestion", context, correlation_id)


class IndexingError(PipelineError):
    """Failure during index write operations."""

    def __init__(
        self,
        message: str = "Indexing failed",
        index_type: str | None = None,
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        ctx = {**(context or {}), "index_type": index_type}
        super().__init__(message, "INDEXING_ERROR", "indexing", ctx, correlation_id)


class RetrievalError(PipelineError):
    """Failure during retrieval operations."""

    def __init__(
        self,
        message: str = "Retrieval failed",
        index_type: str | None = None,
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        ctx = {**(context or {}), "index_type": index_type}
        super().__init__(message, "RETRIEVAL_ERROR", "retrieval", ctx, correlation_id)


class VerificationError(PipelineError):
    """Failure during answer verification."""

    def __init__(
        self,
        message: str = "Verification failed",
        iteration: int | None = None,
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        ctx = {**(context or {}), "iteration": iteration}
        super().__init__(message, "VERIFICATION_ERROR", "verification", ctx, correlation_id)


class GenerationError(PipelineError):
    """Failure during LLM generation."""

    def __init__(
        self,
        message: str = "Generation failed",
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(message, "GENERATION_ERROR", "generation", context, correlation_id)


# ── Infrastructure Errors ───────────────────────────────────────────────────


class EvidenceInsufficiencyError(ISRORAGBaseError):
    """Insufficient evidence to generate a grounded answer."""

    def __init__(
        self,
        message: str = "Insufficient evidence",
        chunks_found: int = 0,
        minimum_required: int = 1,
        correlation_id: str | None = None,
    ) -> None:
        ctx = {
            "chunks_found": chunks_found,
            "minimum_required": minimum_required,
        }
        super().__init__(message, "EVIDENCE_INSUFFICIENT", ctx, correlation_id)


class CircuitBreakerOpenError(ISRORAGBaseError):
    """Circuit breaker is open — service is unavailable."""

    def __init__(
        self,
        service_name: str,
        failure_count: int = 0,
        correlation_id: str | None = None,
    ) -> None:
        msg = f"Circuit breaker open for service '{service_name}'"
        ctx = {"service_name": service_name, "failure_count": failure_count}
        super().__init__(msg, "CIRCUIT_BREAKER_OPEN", ctx, correlation_id)


class StorageError(ISRORAGBaseError):
    """Storage backend failure."""

    def __init__(
        self,
        message: str = "Storage operation failed",
        backend: str | None = None,
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        ctx = {**(context or {}), "backend": backend}
        super().__init__(message, "STORAGE_ERROR", ctx, correlation_id)
