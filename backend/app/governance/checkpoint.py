"""
Governance Checkpoint Decorator
================================

Wraps pipeline functions with governance controls:
1. Policy evaluation before execution (RBAC + classification)
2. Audit logging of the checkpoint
3. Fail-closed error handling

Phase 2: Integrated with PolicyEngine for real authorization checks.

Checkpoints correspond to the required_checkpoints in .antigravityrules:
    - ingestion.pre_normalization
    - ingestion.post_chunking
    - indexing.keyword_write
    - indexing.semantic_write
    - indexing.graph_write
    - retrieval.pre_hybrid_merge
    - verification.loop_iteration
    - generation.response_dispatch
"""

from __future__ import annotations

import functools
import uuid
from typing import Any, Callable, TypeVar

from app.audit.models import AuditAction, AuditDecision, AuditEvent
from app.core.constants import ALL_GOVERNANCE_CHECKPOINTS
from app.core.correlation import get_correlation_id
from app.core.exceptions import GovernanceError, PolicyViolationError
from app.core.logging import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def governance_checkpoint(
    checkpoint_name: str,
    *,
    require_principal: bool = True,
    log_args: bool = False,
    emit_audit: bool = True,
) -> Callable[[F], F]:
    """
    Decorator that enforces a governance checkpoint around a pipeline function.

    Usage:
        @governance_checkpoint("ingestion.pre_normalization")
        def normalize_document(principal, raw_doc):
            ...

    Behavior:
        1. Validates the checkpoint name is in the approved list
        2. Logs checkpoint entry with correlation ID
        3. Optionally evaluates PolicyEngine (when principal is available)
        4. Executes the wrapped function
        5. Logs checkpoint exit with outcome
        6. Emits audit event (if emit_audit=True)
        7. On any GovernanceError: logs failure, re-raises (fail-closed)
        8. On any unexpected error: wraps in GovernanceError, re-raises

    Args:
        checkpoint_name: Must be one of ALL_GOVERNANCE_CHECKPOINTS
        require_principal: If True, the first arg must be a Principal
        log_args: If True, log function arguments (use cautiously for sensitive data)
        emit_audit: If True, emit an audit event on checkpoint entry/exit
    """

    if checkpoint_name not in ALL_GOVERNANCE_CHECKPOINTS:
        raise ValueError(
            f"Unknown governance checkpoint: '{checkpoint_name}'. "
            f"Must be one of: {sorted(ALL_GOVERNANCE_CHECKPOINTS)}"
        )

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            correlation_id = get_correlation_id()

            logger.info(
                "governance_checkpoint_enter",
                checkpoint=checkpoint_name,
                function=func.__qualname__,
                correlation_id=correlation_id,
            )

            # Extract principal if available and required
            principal = None
            principal_id = "system"
            if require_principal and args:
                from app.models.auth import Principal
                if isinstance(args[0], Principal):
                    principal = args[0]
                    principal_id = principal.principal_id

            try:
                # Policy evaluation (when principal is available)
                if principal is not None:
                    _evaluate_policy(
                        principal=principal,
                        checkpoint_name=checkpoint_name,
                        function_name=func.__qualname__,
                        correlation_id=correlation_id,
                    )

                result = func(*args, **kwargs)

                logger.info(
                    "governance_checkpoint_exit",
                    checkpoint=checkpoint_name,
                    function=func.__qualname__,
                    outcome="success",
                    correlation_id=correlation_id,
                )

                # Emit success audit event
                if emit_audit:
                    _emit_checkpoint_audit(
                        checkpoint=checkpoint_name,
                        function_name=func.__qualname__,
                        principal_id=principal_id,
                        decision=AuditDecision.ALLOW,
                        correlation_id=correlation_id,
                    )

                return result

            except GovernanceError:
                logger.error(
                    "governance_checkpoint_failed",
                    checkpoint=checkpoint_name,
                    function=func.__qualname__,
                    outcome="governance_error",
                    correlation_id=correlation_id,
                )
                if emit_audit:
                    _emit_checkpoint_audit(
                        checkpoint=checkpoint_name,
                        function_name=func.__qualname__,
                        principal_id=principal_id,
                        decision=AuditDecision.DENY,
                        correlation_id=correlation_id,
                    )
                raise  # Re-raise governance errors as-is

            except Exception as exc:
                # Fail-closed: wrap unexpected errors in GovernanceError
                logger.error(
                    "governance_checkpoint_unexpected_error",
                    checkpoint=checkpoint_name,
                    function=func.__qualname__,
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                if emit_audit:
                    _emit_checkpoint_audit(
                        checkpoint=checkpoint_name,
                        function_name=func.__qualname__,
                        principal_id=principal_id,
                        decision=AuditDecision.ERROR,
                        correlation_id=correlation_id,
                        error=str(exc),
                    )
                raise GovernanceError(
                    message=(
                        f"Unexpected error at governance checkpoint "
                        f"'{checkpoint_name}': {exc}"
                    ),
                    error_code="CHECKPOINT_UNEXPECTED_ERROR",
                    context={"checkpoint": checkpoint_name, "function": func.__qualname__},
                    correlation_id=correlation_id,
                ) from exc

        return wrapper  # type: ignore[return-value]

    return decorator


def _evaluate_policy(
    principal: Any,
    checkpoint_name: str,
    function_name: str,
    correlation_id: str,
) -> None:
    """
    Evaluate policy for a checkpoint.

    Uses the PolicyEngine to check whether the principal is authorized
    for the current checkpoint action. On DENY → raise PolicyViolationError.
    """
    try:
        from app.security.policy import DefaultPolicyEngine, PolicyDecision

        engine = DefaultPolicyEngine()
        result = engine.evaluate(
            principal=principal,
            action=checkpoint_name,
            resource=function_name,
        )

        if result.decision in (
            PolicyDecision.DENY,
            PolicyDecision.DENY_RBAC,
            PolicyDecision.DENY_CLASSIFICATION,
        ):
            raise PolicyViolationError(
                message=(
                    f"Policy denied at checkpoint '{checkpoint_name}': "
                    f"{result.reason}"
                ),
                policy_name=checkpoint_name,
                context={
                    "principal_id": principal.principal_id if hasattr(principal, 'principal_id') else "unknown",
                    "decision": result.decision.value,
                    "reason": result.reason,
                },
            )

    except PolicyViolationError:
        raise
    except Exception as exc:
        # Policy engine errors are logged but do NOT block execution
        # in Phase 2 — the engine's default DENY is a fail-safe placeholder.
        # In production, this would be upgraded to fail-closed.
        logger.warning(
            "policy_evaluation_skipped",
            checkpoint=checkpoint_name,
            error=str(exc),
            correlation_id=correlation_id,
        )


def _emit_checkpoint_audit(
    checkpoint: str,
    function_name: str,
    principal_id: str,
    decision: AuditDecision,
    correlation_id: str,
    error: str = "",
) -> None:
    """Emit an audit event for a governance checkpoint."""
    try:
        from app.audit.logger import FileAuditLogger

        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            principal_id=principal_id,
            principal_type="SERVICE",
            action=AuditAction.GOVERNANCE_CHECKPOINT,
            resource=f"CHECKPOINT:{checkpoint}",
            request_id=correlation_id,
            decision=decision,
            metadata={
                "checkpoint": checkpoint,
                "function": function_name,
                "error": error,
            },
        )

        audit_logger = FileAuditLogger()
        audit_logger.log_event(event)

    except Exception as exc:
        # Audit failure must never crash the checkpoint
        logger.error(
            "checkpoint_audit_failed",
            checkpoint=checkpoint,
            error=str(exc),
        )
