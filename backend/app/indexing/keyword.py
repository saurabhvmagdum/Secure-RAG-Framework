"""
Keyword Index Writer — OpenSearch Adapter
==========================================

Writes document chunks to OpenSearch for BM25 lexical retrieval.
Governance checkpoint: indexing.keyword_write

Features:
- Index-per-sensitivity partitioning (isro-rag-{sensitivity}-{domain})
- SHA-256 integrity checksums per indexed document
- Classification-aware eligibility check (SECRET data excluded)
- Tokenization metadata for downstream retrieval
- Circuit breaker for OpenSearch connectivity
- Audit event emission on every write
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from app.audit.logger import AuditLogger, FileAuditLogger
from app.audit.models import AuditAction, AuditDecision, AuditEvent
from app.core.correlation import get_correlation_id
from app.core.exceptions import ClassificationError, IndexingError
from app.core.logging import get_logger
from app.governance.checkpoint import governance_checkpoint
from app.governance.classification import ClassificationEngine, DefaultClassificationEngine
from app.models.document import Chunk
from app.models.index import KeywordIndexDocument
from app.models.metadata import SensitivityLevel
from app.utils.circuit_breaker import CircuitBreaker

logger = get_logger(__name__)


@runtime_checkable
class KeywordIndexWriter(Protocol):
    """Protocol for writing to the BM25 lexical index."""

    def index_chunk(self, chunk: Chunk) -> KeywordIndexDocument:
        ...

    def index_batch(self, chunks: list[Chunk]) -> list[KeywordIndexDocument]:
        ...

    def delete_by_doc_id(self, doc_id: str) -> int:
        ...

    def health_check(self) -> bool:
        ...


class OpenSearchKeywordIndexWriter:
    """
    OpenSearch adapter for BM25 keyword indexing.

    Index strategy:
    - Index name: isro-rag-kw-{sensitivity_level}-{domain_tag}
    - Document ID: chunk_id (deterministic, idempotent upsert)
    - Integrity: SHA-256 checksum of chunk text

    Classification enforcement:
    - SECRET data is NOT eligible for keyword index
    - Validated before every write via ClassificationEngine
    """

    def __init__(
        self,
        opensearch_client: Any | None = None,
        classification_engine: ClassificationEngine | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self._client = opensearch_client  # None in Phase 2 skeleton
        self._classification = classification_engine or DefaultClassificationEngine()
        self._audit = audit_logger or FileAuditLogger()
        self._circuit_breaker = CircuitBreaker(
            service_name="opensearch",
            failure_threshold=5,
            recovery_timeout_seconds=30.0,
        )

    @governance_checkpoint(
        "indexing.keyword_write", require_principal=False
    )
    def index_chunk(self, chunk: Chunk) -> KeywordIndexDocument:
        """
        Index a single chunk into OpenSearch.

        Steps:
        1. Validate classification eligibility
        2. Compute integrity checksum
        3. Build index document
        4. Write to OpenSearch via circuit breaker
        5. Emit audit event
        """
        # 1. Classification eligibility check
        if not self._classification.validate_index_eligibility(
            chunk.metadata.sensitivity_level, "keyword"
        ):
            raise ClassificationError(
                message=(
                    f"Chunk {chunk.chunk_id} is classified as "
                    f"{chunk.metadata.sensitivity_level.value} — "
                    f"not eligible for keyword index"
                ),
                context={
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.doc_id,
                    "sensitivity": chunk.metadata.sensitivity_level.value,
                },
            )

        # 2. Compute integrity checksum
        checksum = self._compute_checksum(chunk.text)

        # 3. Build index document
        index_name = self._resolve_index_name(chunk)

        index_doc = KeywordIndexDocument(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            index_name=index_name,
            text=chunk.text,
            tokens=[],  # Tokenization handled by OpenSearch analyzer
            checksum=checksum,
            metadata=chunk.metadata,
        )

        # 4. Write to OpenSearch
        self._write_to_opensearch(index_doc)

        # 5. Audit event
        self._emit_write_audit(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            index_name=index_name,
            sensitivity=chunk.metadata.sensitivity_level.value,
        )

        logger.info(
            "keyword_index_write",
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            index_name=index_name,
            checksum=checksum[:16],
        )

        return index_doc

    @governance_checkpoint(
        "indexing.keyword_write", require_principal=False
    )
    def index_batch(self, chunks: list[Chunk]) -> list[KeywordIndexDocument]:
        """Index multiple chunks. Ineligible chunks are filtered with error logging."""
        results: list[KeywordIndexDocument] = []

        eligible_chunks = []
        for chunk in chunks:
            if self._classification.validate_index_eligibility(
                chunk.metadata.sensitivity_level, "keyword"
            ):
                eligible_chunks.append(chunk)
            else:
                logger.warning(
                    "keyword_index_skip_ineligible",
                    chunk_id=chunk.chunk_id,
                    sensitivity=chunk.metadata.sensitivity_level.value,
                )

        for chunk in eligible_chunks:
            try:
                # Skip governance checkpoint for individual items in batch
                checksum = self._compute_checksum(chunk.text)
                index_name = self._resolve_index_name(chunk)

                index_doc = KeywordIndexDocument(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    index_name=index_name,
                    text=chunk.text,
                    tokens=[],
                    checksum=checksum,
                    metadata=chunk.metadata,
                )

                self._write_to_opensearch(index_doc)
                results.append(index_doc)

            except Exception as exc:
                logger.error(
                    "keyword_index_batch_item_failed",
                    chunk_id=chunk.chunk_id,
                    error=str(exc),
                )

        # Single batch audit event
        if results:
            self._emit_write_audit(
                chunk_id=f"batch:{len(results)}",
                doc_id=results[0].doc_id if results else "",
                index_name="batch",
                sensitivity="mixed",
                extra={"batch_size": len(results), "total_submitted": len(chunks)},
            )

        logger.info(
            "keyword_index_batch_complete",
            total=len(chunks),
            indexed=len(results),
            skipped=len(chunks) - len(eligible_chunks),
        )

        return results

    def delete_by_doc_id(self, doc_id: str) -> int:
        """
        Delete all keyword index entries for a document.

        In production, executes delete-by-query against all keyword indices.
        """
        logger.info("keyword_index_delete", doc_id=doc_id)

        if self._client is None:
            logger.warning("keyword_index_delete_no_client", doc_id=doc_id)
            return 0

        # TODO: Execute OpenSearch delete_by_query across all keyword indices
        # query = {"match": {"doc_id": doc_id}}
        # response = self._client.delete_by_query(index="isro-rag-kw-*", body={"query": query})
        # return response.get("deleted", 0)
        return 0

    def health_check(self) -> bool:
        """Check OpenSearch connectivity."""
        if self._client is None:
            return False
        try:
            return self._circuit_breaker.call(
                lambda: self._client.ping()
            )
        except Exception:
            return False

    def _write_to_opensearch(self, doc: KeywordIndexDocument) -> None:
        """Write an index document to OpenSearch."""
        if self._client is None:
            logger.debug(
                "keyword_index_dry_run",
                chunk_id=doc.chunk_id,
                index_name=doc.index_name,
            )
            return

        try:
            body = {
                "chunk_id": doc.chunk_id,
                "doc_id": doc.doc_id,
                "text": doc.text,
                "checksum": doc.checksum,
                "domain_tag": doc.metadata.domain_tag.value,
                "sensitivity_level": doc.metadata.sensitivity_level.value,
                "version": doc.metadata.version,
                "origin": doc.metadata.origin,
                "indexed_at": datetime.now(tz=timezone.utc).isoformat(),
            }

            self._circuit_breaker.call(
                self._client.index,
                index=doc.index_name,
                id=doc.chunk_id,
                body=body,
            )

        except Exception as exc:
            raise IndexingError(
                message=f"OpenSearch write failed for chunk {doc.chunk_id}: {exc}",
                context={
                    "chunk_id": doc.chunk_id,
                    "index_name": doc.index_name,
                },
            ) from exc

    @staticmethod
    def _resolve_index_name(chunk: Chunk) -> str:
        """
        Resolve the target index name based on sensitivity and domain.

        Format: isro-rag-kw-{sensitivity}-{domain}
        """
        sensitivity = chunk.metadata.sensitivity_level.value.lower()
        domain = chunk.metadata.domain_tag.value.lower()
        return f"isro-rag-kw-{sensitivity}-{domain}"

    @staticmethod
    def _compute_checksum(text: str) -> str:
        """Compute SHA-256 checksum of chunk text for integrity verification."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _emit_write_audit(
        self,
        chunk_id: str,
        doc_id: str,
        index_name: str,
        sensitivity: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Emit audit event for index write."""
        try:
            event = AuditEvent(
                event_id=str(uuid.uuid4()),
                principal_id="indexing-service",
                principal_type="SERVICE",
                action=AuditAction.INDEX_WRITE,
                resource=f"INDEX:KEYWORD:{index_name}",
                request_id=get_correlation_id(),
                decision=AuditDecision.ALLOW,
                metadata={
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "index_name": index_name,
                    "index_type": "keyword",
                    "sensitivity": sensitivity,
                    **(extra or {}),
                },
            )
            self._audit.log_event(event)
        except Exception as exc:
            logger.error("keyword_audit_failed", error=str(exc))
