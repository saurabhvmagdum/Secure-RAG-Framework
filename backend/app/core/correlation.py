"""
Correlation ID Management
=========================

Generates and propagates correlation IDs across the request lifecycle.
Every log entry, audit event, and inter-service call must carry the correlation ID
for end-to-end traceability.

Uses contextvars for thread-safe, async-safe propagation within a single request.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any

# ── Context Variable ────────────────────────────────────────────────────────
# Holds the current correlation ID for the active request/task context.
_correlation_id_var: ContextVar[str] = ContextVar(
    "correlation_id", default=""
)

# Optional: secondary correlation IDs for sub-operations (retrieval, verification, etc.)
_sub_correlation_ids_var: ContextVar[list[str]] = ContextVar(
    "sub_correlation_ids", default=[]
)


def generate_correlation_id() -> str:
    """Generate a new UUID4-based correlation ID."""
    return str(uuid.uuid4())


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID for the current context."""
    _correlation_id_var.set(correlation_id)


def get_correlation_id() -> str:
    """
    Retrieve the current correlation ID.

    Returns an empty string if no correlation ID has been set (should not
    happen in normal request flow — the middleware sets it).
    """
    return _correlation_id_var.get()


def add_sub_correlation_id(sub_id: str) -> None:
    """
    Add a sub-operation correlation ID (e.g., for retrieval or verification steps).

    These are collected and included in audit events for cross-referencing.
    """
    current = _sub_correlation_ids_var.get()
    # ContextVar default is shared; create a copy on first write
    if not current:
        current = []
        _sub_correlation_ids_var.set(current)
    current.append(sub_id)


def get_sub_correlation_ids() -> list[str]:
    """Retrieve all sub-operation correlation IDs for the current context."""
    return list(_sub_correlation_ids_var.get())


def reset_correlation_context() -> None:
    """Reset all correlation state — call at the end of a request."""
    _correlation_id_var.set("")
    _sub_correlation_ids_var.set([])


def correlation_context() -> dict[str, Any]:
    """
    Return the full correlation context as a dict, suitable for injection
    into log entries and audit events.
    """
    return {
        "correlation_id": get_correlation_id(),
        "sub_correlation_ids": get_sub_correlation_ids(),
    }
