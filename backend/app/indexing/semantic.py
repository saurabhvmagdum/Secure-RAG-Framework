"""
Semantic Index Writer — Qdrant Adapter
========================================

Writes document chunk embeddings to Qdrant for vector similarity retrieval.
Governance checkpoint: indexing.semantic_write

Features:
- Collection-per-sensitivity partitioning
- Embedding model provenance tracking (model_id in payload)
- Classification-aware eligibility check
- Metadata payload for filtered search
- Circuit breaker for Qdrant connectivity
- Audit event emission on every write
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from app.audit.logger import AuditLogger, FileAuditLogger
from app.audit.models import AuditAction, AuditDecision, AuditEvent
from app.core.correlation import get_correlation_id
from app.core.exceptions import IndexingError
from app.core.logging import get_logger
from app.governance.checkpoint import governance_checkpoint
from app.governance.classification import ClassificationEngine, DefaultClassificationEngine
from app.models.document import Chunk
from app.models.index import SemanticIndexDocument
from app.utils.circuit_breaker import CircuitBreaker

logger = get_logger(__name__)


@runtime_checkable
class SemanticIndexWriter(Protocol):
    """Protocol for writing to the semantic vector index."""

    def index_chunk(self, chunk: Chunk) -> SemanticIndexDocument:
        ...

    def index_batch(self, chunks: list[Chunk]) -> list[SemanticIndexDocument]:
        ...

    def delete_by_doc_id(self, doc_id: str) -> int:
        ...

    def health_check(self) -> bool:
        ...


class QdrantSemanticIndexWriter:
    """
    Qdrant adapter for semantic vector indexing.

    Collection strategy:
    - Collection name: isro-rag-sem-{sensitivity_level}
    - Point ID: UUID from chunk_id
    - Payload: governed metadata for filtered search

    Embedding strategy:
    - Uses on-prem embedding model (loaded from EMBEDDING_STORE_PATH)
    - Embedding model_id tracked in every index document for provenance
    - Phase 2 skeleton: embedding generation is delegated to an EmbeddingService
    """

    def __init__(
        self,
        qdrant_client: Any | None = None,
        embedding_service: Any | None = None,
        classification_engine: ClassificationEngine | None = None,
        audit_logger: AuditLogger | None = None,
        embedding_model_id: str = "isro-domain-encoder-v1",
        vector_size: int = 768,
    ) -> None:
        self._client = qdrant_client  # None in Phase 2 skeleton
        self._embedder = embedding_service  # None in Phase 2 skeleton
        self._classification = classification_engine or DefaultClassificationEngine()
        self._audit = audit_logger or FileAuditLogger()
        self._model_id = embedding_model_id
        self._vector_size = vector_size
        self._circuit_breaker = CircuitBreaker(
            service_name="qdrant",
            failure_threshold=5,
            recovery_timeout_seconds=30.0,
        )

    @governance_checkpoint(
        "indexing.semantic_write", require_principal=False
    )
    def index_chunk(self, chunk: Chunk) -> SemanticIndexDocument:
        """
        Generate embedding and index a chunk into Qdrant.

        Steps:
        1. Validate classification eligibility
        2. Generate embedding vector via on-prem model
        3. Build index document with metadata payload
        4. Upsert to Qdrant via circuit breaker
        5. Emit audit event
        """
        # 1. Classification eligibility
        if not self._classification.validate_index_eligibility(
            chunk.metadata.sensitivity_level, "semantic"
        ):
            raise IndexingError(
                message=(
                    f"Chunk {chunk.chunk_id} not eligible for semantic index "
                    f"at sensitivity {chunk.metadata.sensitivity_level.value}"
                ),
                context={"chunk_id": chunk.chunk_id},
            )

        # 2. Generate embedding
        embedding = self._generate_embedding(chunk.text)

        # 3. Build index document
        collection_name = self._resolve_collection_name(chunk)

        index_doc = SemanticIndexDocument(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            collection_name=collection_name,
            embedding=embedding,
            embedding_model_id=self._model_id,
            metadata=chunk.metadata,
        )

        # 4. Upsert to Qdrant
        self._upsert_to_qdrant(index_doc)

        # 5. Audit event
        self._emit_write_audit(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            collection_name=collection_name,
            sensitivity=chunk.metadata.sensitivity_level.value,
        )

        logger.info(
            "semantic_index_write",
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            collection=collection_name,
            embedding_dim=len(embedding),
        )

        return index_doc

    @governance_checkpoint(
        "indexing.semantic_write", require_principal=False
    )
    def index_batch(self, chunks: list[Chunk]) -> list[SemanticIndexDocument]:
        """Index multiple chunks with batch embedding generation."""
        results: list[SemanticIndexDocument] = []

        # Filter eligible chunks
        eligible = [
            c for c in chunks
            if self._classification.validate_index_eligibility(
                c.metadata.sensitivity_level, "semantic"
            )
        ]

        skipped = len(chunks) - len(eligible)
        if skipped > 0:
            logger.warning(
                "semantic_index_batch_skip",
                skipped=skipped,
                reason="classification_ineligible",
            )

        # Generate embeddings (batch)
        texts = [c.text for c in eligible]
        embeddings = self._generate_embeddings_batch(texts)

        for chunk, embedding in zip(eligible, embeddings):
            try:
                collection_name = self._resolve_collection_name(chunk)

                index_doc = SemanticIndexDocument(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    collection_name=collection_name,
                    embedding=embedding,
                    embedding_model_id=self._model_id,
                    metadata=chunk.metadata,
                )

                self._upsert_to_qdrant(index_doc)
                results.append(index_doc)

            except Exception as exc:
                logger.error(
                    "semantic_index_batch_item_failed",
                    chunk_id=chunk.chunk_id,
                    error=str(exc),
                )

        if results:
            self._emit_write_audit(
                chunk_id=f"batch:{len(results)}",
                doc_id=results[0].doc_id if results else "",
                collection_name="batch",
                sensitivity="mixed",
                extra={"batch_size": len(results)},
            )

        logger.info(
            "semantic_index_batch_complete",
            total=len(chunks),
            indexed=len(results),
            skipped=skipped,
        )

        return results

    def delete_by_doc_id(self, doc_id: str) -> int:
        """Delete all semantic index entries for a document."""
        logger.info("semantic_index_delete", doc_id=doc_id)

        if self._client is None:
            return 0

        # TODO: Execute Qdrant delete_by_filter across all collections
        return 0

    def health_check(self) -> bool:
        """Check Qdrant connectivity."""
        if self._client is None:
            return False
        try:
            return self._circuit_breaker.call(
                lambda: self._client.get_collections() is not None
            )
        except Exception:
            return False

    def _generate_embedding(self, text: str) -> list[float]:
        """
        Generate embedding for a single text using on-prem model.

        Phase 2 skeleton: Returns zero vector when no embedder is configured.
        Production: delegates to EmbeddingService.
        """
        if self._embedder is not None:
            try:
                return self._embedder.embed(text)
            except Exception as exc:
                raise IndexingError(
                    message=f"Embedding generation failed: {exc}",
                    context={"text_length": len(text)},
                ) from exc

        # Phase 2 skeleton: zero vector placeholder
        logger.debug("semantic_embedding_placeholder", text_len=len(text))
        return [0.0] * self._vector_size

    def _generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        if self._embedder is not None:
            try:
                return self._embedder.embed_batch(texts)
            except Exception as exc:
                raise IndexingError(
                    message=f"Batch embedding generation failed: {exc}",
                    context={"batch_size": len(texts)},
                ) from exc

        # Phase 2 skeleton: zero vector placeholders
        return [[0.0] * self._vector_size for _ in texts]

    def _upsert_to_qdrant(self, doc: SemanticIndexDocument) -> None:
        """Upsert a vector point to Qdrant."""
        if self._client is None:
            logger.debug(
                "semantic_index_dry_run",
                chunk_id=doc.chunk_id,
                collection=doc.collection_name,
            )
            return

        try:
            # Convert chunk_id to UUID for Qdrant point ID
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, doc.chunk_id))

            payload = {
                "chunk_id": doc.chunk_id,
                "doc_id": doc.doc_id,
                "domain_tag": doc.metadata.domain_tag.value,
                "sensitivity_level": doc.metadata.sensitivity_level.value,
                "version": doc.metadata.version,
                "origin": doc.metadata.origin,
                "embedding_model_id": doc.embedding_model_id,
                "indexed_at": datetime.now(tz=timezone.utc).isoformat(),
            }

            self._circuit_breaker.call(
                self._client.upsert,
                collection_name=doc.collection_name,
                points=[{
                    "id": point_id,
                    "vector": doc.embedding,
                    "payload": payload,
                }],
            )

        except Exception as exc:
            raise IndexingError(
                message=f"Qdrant upsert failed for chunk {doc.chunk_id}: {exc}",
                context={"chunk_id": doc.chunk_id, "collection": doc.collection_name},
            ) from exc

    @staticmethod
    def _resolve_collection_name(chunk: Chunk) -> str:
        """
        Resolve the target Qdrant collection based on sensitivity.

        Format: isro-rag-sem-{sensitivity}
        """
        sensitivity = chunk.metadata.sensitivity_level.value.lower()
        return f"isro-rag-sem-{sensitivity}"

    def _emit_write_audit(
        self,
        chunk_id: str,
        doc_id: str,
        collection_name: str,
        sensitivity: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Emit audit event for semantic index write."""
        try:
            event = AuditEvent(
                event_id=str(uuid.uuid4()),
                principal_id="indexing-service",
                principal_type="SERVICE",
                action=AuditAction.INDEX_WRITE,
                resource=f"INDEX:SEMANTIC:{collection_name}",
                request_id=get_correlation_id(),
                decision=AuditDecision.ALLOW,
                metadata={
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "collection": collection_name,
                    "index_type": "semantic",
                    "sensitivity": sensitivity,
                    "model_id": self._model_id,
                    **(extra or {}),
                },
            )
            self._audit.log_event(event)
        except Exception as exc:
            logger.error("semantic_audit_failed", error=str(exc))
