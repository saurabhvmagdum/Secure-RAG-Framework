"""
Tri-Index Write Orchestrator
==============================

Coordinates writes across all three indices (keyword, semantic, graph)
for a given set of document chunks.

Responsibilities:
- Fan-out writes to keyword, semantic, and graph index writers
- Enforce classification-aware eligibility per index
- Isolate failures per index — a failure in one index does NOT block others
- Aggregate results and produce a structured write report
- Emit consolidated audit event for the tri-index write operation
- Support both single-document and batch-document flows
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.audit.logger import AuditLogger, FileAuditLogger
from app.audit.models import AuditAction, AuditDecision, AuditEvent
from app.core.correlation import get_correlation_id
from app.core.logging import get_logger
from app.governance.classification import ClassificationEngine, DefaultClassificationEngine
from app.indexing.keyword import KeywordIndexWriter, OpenSearchKeywordIndexWriter
from app.indexing.semantic import QdrantSemanticIndexWriter, SemanticIndexWriter
from app.indexing.graph import GraphIndexWriter, Neo4jGraphIndexWriter
from app.models.document import Chunk, NormalizedDocument

logger = get_logger(__name__)


class IndexWriteStatus(BaseModel):
    """Status of a single index write operation."""

    index_type: str = Field(..., description="keyword | semantic | graph")
    status: str = Field(..., description="SUCCESS | FAILED | SKIPPED")
    items_written: int = Field(default=0, ge=0)
    items_skipped: int = Field(default=0, ge=0)
    error: str | None = Field(default=None)

    model_config = {"extra": "forbid"}


class TriIndexWriteResult(BaseModel):
    """Aggregated result of writing to all three indices."""

    doc_id: str = Field(..., description="Document ID that was indexed")
    total_chunks: int = Field(default=0, ge=0)
    keyword: IndexWriteStatus = Field(...)
    semantic: IndexWriteStatus = Field(...)
    graph: IndexWriteStatus = Field(...)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )

    model_config = {"extra": "forbid"}

    @property
    def all_succeeded(self) -> bool:
        """True if all three indices wrote successfully."""
        return (
            self.keyword.status == "SUCCESS"
            and self.semantic.status == "SUCCESS"
            and self.graph.status == "SUCCESS"
        )

    @property
    def any_failed(self) -> bool:
        """True if any index write failed."""
        return any(
            s.status == "FAILED"
            for s in [self.keyword, self.semantic, self.graph]
        )


class IndexingOrchestrator:
    """
    Orchestrates tri-index writes for document chunks.

    Write strategy:
    1. For each index type, check classification eligibility
    2. Write eligible chunks to the index
    3. Isolate failures — a failure in one index does NOT affect others
    4. Produce a structured TriIndexWriteResult
    5. Emit consolidated audit event

    Used by the IngestionPipeline as the index_writer_callback.
    """

    def __init__(
        self,
        keyword_writer: KeywordIndexWriter | None = None,
        semantic_writer: SemanticIndexWriter | None = None,
        graph_writer: GraphIndexWriter | None = None,
        classification_engine: ClassificationEngine | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self._keyword = keyword_writer or OpenSearchKeywordIndexWriter()
        self._semantic = semantic_writer or QdrantSemanticIndexWriter()
        self._graph = graph_writer or Neo4jGraphIndexWriter()
        self._classification = classification_engine or DefaultClassificationEngine()
        self._audit = audit_logger or FileAuditLogger()

    def index_document_chunks(
        self,
        document: NormalizedDocument,
        chunks: list[Chunk],
    ) -> TriIndexWriteResult:
        """
        Write document chunks to all three indices.

        This is the primary entry point for the ingestion pipeline.
        Each index write is independent — failures are isolated.
        """
        correlation_id = get_correlation_id()

        logger.info(
            "tri_index_write_start",
            doc_id=document.doc_id,
            total_chunks=len(chunks),
            sensitivity=document.metadata.sensitivity_level.value,
            domain=document.metadata.domain_tag.value,
            correlation_id=correlation_id,
        )

        # Fan-out writes to each index
        keyword_status = self._write_keyword_index(chunks)
        semantic_status = self._write_semantic_index(chunks)
        graph_status = self._write_graph_index(chunks)

        result = TriIndexWriteResult(
            doc_id=document.doc_id,
            total_chunks=len(chunks),
            keyword=keyword_status,
            semantic=semantic_status,
            graph=graph_status,
        )

        # Emit consolidated audit
        self._emit_consolidated_audit(document.doc_id, result, correlation_id)

        logger.info(
            "tri_index_write_complete",
            doc_id=document.doc_id,
            keyword=keyword_status.status,
            semantic=semantic_status.status,
            graph=graph_status.status,
            all_succeeded=result.all_succeeded,
        )

        return result

    def __call__(
        self,
        document: NormalizedDocument,
        chunks: list[Chunk],
    ) -> TriIndexWriteResult:
        """Callable interface for use as IngestionPipeline callback."""
        return self.index_document_chunks(document, chunks)

    def _write_keyword_index(self, chunks: list[Chunk]) -> IndexWriteStatus:
        """Write chunks to keyword (BM25) index."""
        try:
            # Pre-filter by classification eligibility
            eligible = [
                c for c in chunks
                if self._classification.validate_index_eligibility(
                    c.metadata.sensitivity_level, "keyword"
                )
            ]
            skipped = len(chunks) - len(eligible)

            if not eligible:
                return IndexWriteStatus(
                    index_type="keyword",
                    status="SKIPPED",
                    items_skipped=skipped,
                )

            results = self._keyword.index_batch(eligible)

            return IndexWriteStatus(
                index_type="keyword",
                status="SUCCESS",
                items_written=len(results),
                items_skipped=skipped,
            )

        except Exception as exc:
            logger.error(
                "keyword_index_write_failed",
                error=str(exc),
                total_chunks=len(chunks),
            )
            return IndexWriteStatus(
                index_type="keyword",
                status="FAILED",
                error=str(exc),
            )

    def _write_semantic_index(self, chunks: list[Chunk]) -> IndexWriteStatus:
        """Write chunks to semantic (vector) index."""
        try:
            eligible = [
                c for c in chunks
                if self._classification.validate_index_eligibility(
                    c.metadata.sensitivity_level, "semantic"
                )
            ]
            skipped = len(chunks) - len(eligible)

            if not eligible:
                return IndexWriteStatus(
                    index_type="semantic",
                    status="SKIPPED",
                    items_skipped=skipped,
                )

            results = self._semantic.index_batch(eligible)

            return IndexWriteStatus(
                index_type="semantic",
                status="SUCCESS",
                items_written=len(results),
                items_skipped=skipped,
            )

        except Exception as exc:
            logger.error(
                "semantic_index_write_failed",
                error=str(exc),
                total_chunks=len(chunks),
            )
            return IndexWriteStatus(
                index_type="semantic",
                status="FAILED",
                error=str(exc),
            )

    def _write_graph_index(self, chunks: list[Chunk]) -> IndexWriteStatus:
        """Write chunks to knowledge graph index."""
        try:
            eligible = [
                c for c in chunks
                if self._classification.validate_index_eligibility(
                    c.metadata.sensitivity_level, "graph"
                )
            ]
            skipped = len(chunks) - len(eligible)

            if not eligible:
                return IndexWriteStatus(
                    index_type="graph",
                    status="SKIPPED",
                    items_skipped=skipped,
                )

            total_nodes = 0
            total_edges = 0

            for chunk in eligible:
                try:
                    nodes, edges = self._graph.index_chunk(chunk)
                    total_nodes += len(nodes)
                    total_edges += len(edges)
                except Exception as exc:
                    logger.error(
                        "graph_index_chunk_failed",
                        chunk_id=chunk.chunk_id,
                        error=str(exc),
                    )

            return IndexWriteStatus(
                index_type="graph",
                status="SUCCESS",
                items_written=total_nodes + total_edges,
                items_skipped=skipped,
            )

        except Exception as exc:
            logger.error(
                "graph_index_write_failed",
                error=str(exc),
                total_chunks=len(chunks),
            )
            return IndexWriteStatus(
                index_type="graph",
                status="FAILED",
                error=str(exc),
            )

    def _emit_consolidated_audit(
        self,
        doc_id: str,
        result: TriIndexWriteResult,
        correlation_id: str,
    ) -> None:
        """Emit a single audit event summarizing the tri-index write."""
        try:
            decision = (
                AuditDecision.ALLOW if result.all_succeeded
                else AuditDecision.ERROR if result.any_failed
                else AuditDecision.ALLOW
            )

            event = AuditEvent(
                event_id=str(uuid.uuid4()),
                principal_id="indexing-orchestrator",
                principal_type="SERVICE",
                action=AuditAction.INDEX_WRITE,
                resource=f"DOC:{doc_id}",
                request_id=correlation_id,
                decision=decision,
                metadata={
                    "doc_id": doc_id,
                    "total_chunks": result.total_chunks,
                    "keyword_status": result.keyword.status,
                    "keyword_written": result.keyword.items_written,
                    "semantic_status": result.semantic.status,
                    "semantic_written": result.semantic.items_written,
                    "graph_status": result.graph.status,
                    "graph_written": result.graph.items_written,
                },
            )
            self._audit.log_event(event)

        except Exception as exc:
            logger.error("tri_index_audit_failed", error=str(exc))
