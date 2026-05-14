"""
Vector Store Protocol
======================

Abstraction over Qdrant for vector CRUD operations.
Provides collection management, upsert, search, and deletion
with sensitivity-aware partitioning.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.evidence import EvidenceChunk
from app.models.index import SemanticIndexDocument
from app.storage.base import StorageAdapter


@runtime_checkable
class VectorStore(StorageAdapter, Protocol):
    """
    Protocol for vector storage operations.

    Implementations must:
    - Manage Qdrant collections partitioned by sensitivity
    - Upsert vectors with metadata payloads
    - Execute filtered similarity search
    - Use circuit breaker for all Qdrant calls
    """

    def upsert(self, document: SemanticIndexDocument) -> None:
        """Upsert a vector with metadata payload."""
        ...

    def upsert_batch(self, documents: list[SemanticIndexDocument]) -> None:
        """Batch upsert vectors."""
        ...

    def search(
        self,
        query_vector: list[float],
        top_k: int = 20,
        sensitivity_filter: str | None = None,
        domain_filter: str | None = None,
    ) -> list[EvidenceChunk]:
        """
        Execute filtered similarity search.

        Args:
            query_vector: Dense query embedding
            top_k: Maximum results to return
            sensitivity_filter: Filter by sensitivity level
            domain_filter: Filter by domain tag

        Returns:
            Ranked list of EvidenceChunk results
        """
        ...

    def delete_by_doc_id(self, doc_id: str) -> int:
        """Delete all vectors for a document. Returns count deleted."""
        ...

    def collection_exists(self, collection_name: str) -> bool:
        """Check if a collection exists."""
        ...

    def create_collection(
        self, collection_name: str, vector_size: int
    ) -> None:
        """Create a new collection with the specified vector size."""
        ...


# TODO: Phase 2 — Implement QdrantVectorStore:
#   - Qdrant client with circuit breaker
#   - Collection management with sensitivity partitioning
#   - Metadata payload filtering
#   - Batch upsert optimization
