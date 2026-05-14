"""
Document Store Protocol
========================

Persistence for RawDocument and NormalizedDocument objects.
Provides CRUD operations with classification-aware access control.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.document import NormalizedDocument, RawDocument
from app.storage.base import StorageAdapter


@runtime_checkable
class DocumentStore(StorageAdapter, Protocol):
    """
    Protocol for document persistence.

    Implementations must:
    - Store raw and normalized documents
    - Enforce sensitivity-based access control on reads
    - Support lookup by doc_id and external_id
    - Use circuit breaker for all I/O
    """

    def store_raw(self, document: RawDocument) -> str:
        """
        Persist a raw document.

        Returns:
            Storage key / identifier
        """
        ...

    def store_normalized(self, document: NormalizedDocument) -> str:
        """
        Persist a normalized document.

        Returns:
            The doc_id of the stored document
        """
        ...

    def get_by_doc_id(self, doc_id: str) -> NormalizedDocument | None:
        """Retrieve a normalized document by doc_id."""
        ...

    def get_by_external_id(
        self, external_id: str, source_system: str
    ) -> NormalizedDocument | None:
        """Retrieve a normalized document by external_id + source_system."""
        ...

    def exists(self, doc_id: str) -> bool:
        """Check if a document exists."""
        ...

    def delete(self, doc_id: str) -> bool:
        """Delete a document and return True if it existed."""
        ...


# TODO: Phase 2 — Implement FileSystemDocumentStore or PostgresDocumentStore
