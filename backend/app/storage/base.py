"""
Base Storage Adapter Protocol
===============================

All storage adapters (document store, vector store, graph store) must
implement this base protocol. Circuit breaker protection is mandatory
for all I/O operations.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageAdapter(Protocol):
    """
    Base protocol for all storage backends.

    Every storage adapter must:
    - Provide a health check
    - Use circuit breaker for all I/O
    - Support graceful shutdown
    - Log all operations via structured logging
    """

    def health_check(self) -> bool:
        """
        Check if the storage backend is reachable and operational.

        Returns True if healthy, False otherwise.
        Must not raise exceptions.
        """
        ...

    def is_available(self) -> bool:
        """
        Check if the storage backend is available (circuit breaker not open).
        """
        ...

    async def shutdown(self) -> None:
        """Gracefully close connections and release resources."""
        ...


# TODO: Phase 2 — Implement base adapter with circuit breaker mixin
