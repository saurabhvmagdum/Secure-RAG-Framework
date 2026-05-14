"""
Ingestion Pipeline Orchestrator
================================

Coordinates the full ingestion flow:
    RawDocument → Parser → Normalizer → Chunker → Index Writers

Responsibilities:
- Apply source-specific parser before normalization
- Enforce governance checkpoints at each stage
- Emit audit events for every ingestion
- Coordinate tri-index writes via IndexingOrchestrator
- Hard-fail on any validation or policy error
- Support batch ingestion with per-document error isolation
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.audit.logger import AuditLogger, FileAuditLogger
from app.audit.models import AuditAction, AuditDecision, AuditEvent
from app.core.correlation import generate_correlation_id, get_correlation_id, set_correlation_id
from app.core.exceptions import IngestionError
from app.core.logging import get_logger
from app.ingestion.chunker import Chunker, DefaultChunker
from app.ingestion.config import IngestionSettings
from app.ingestion.normalizer import DefaultNormalizer, Normalizer
from app.ingestion.parsers import ParserRegistry, parser_registry
from app.models.document import Chunk, NormalizedDocument, RawDocument

logger = get_logger(__name__)


class IngestionResult(BaseModel):
    """Result of ingesting a single document."""

    doc_id: str = Field(..., description="Assigned doc_id")
    external_id: str = Field(..., description="Source external_id")
    source_system: str = Field(..., description="Source system")
    status: str = Field(..., description="SUCCESS | FAILED")
    chunks_created: int = Field(default=0, ge=0)
    error: str | None = Field(default=None, description="Error message if failed")
    domain_tag: str = Field(default="", description="Assigned domain_tag")
    sensitivity_level: str = Field(default="", description="Assigned sensitivity")

    model_config = {"extra": "forbid"}


class BatchIngestionResult(BaseModel):
    """Result of a batch ingestion run."""

    batch_id: str = Field(..., description="Unique batch identifier")
    total_submitted: int = Field(default=0, ge=0)
    total_succeeded: int = Field(default=0, ge=0)
    total_failed: int = Field(default=0, ge=0)
    total_chunks: int = Field(default=0, ge=0)
    results: list[IngestionResult] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    completed_at: datetime | None = Field(default=None)

    model_config = {"extra": "forbid"}


class IngestionPipeline:
    """
    Orchestrates the complete ingestion flow.

    Called for both single-document and batch-document ingestion.
    Each document passes through:
        1. Source-specific parsing (structural extraction)
        2. Normalization (UUID generation, text cleanup, metadata tagging)
        3. Chunking (section-aware splitting, metadata propagation)
        4. Tri-index writes (keyword, semantic, graph) — via callback

    Governance checkpoints fire at normalization and chunking stages.
    Audit events are emitted for every document processed.
    """

    def __init__(
        self,
        normalizer: Normalizer | None = None,
        chunker: Chunker | None = None,
        parser_reg: ParserRegistry | None = None,
        audit_logger: AuditLogger | None = None,
        settings: IngestionSettings | None = None,
        index_writer_callback: Any | None = None,
    ) -> None:
        """
        Args:
            normalizer: Document normalizer (default: DefaultNormalizer)
            chunker: Document chunker (default: DefaultChunker)
            parser_reg: Parser registry (default: global parser_registry)
            audit_logger: Audit logger (default: FileAuditLogger)
            settings: Ingestion settings
            index_writer_callback: Optional callback(doc, chunks) → None
                                   for tri-index writes. Set by IndexingOrchestrator.
        """
        self._normalizer: Normalizer = normalizer or DefaultNormalizer()
        self._chunker: Chunker = chunker or DefaultChunker()
        self._parser_registry = parser_reg or parser_registry
        self._audit = audit_logger or FileAuditLogger()
        self._settings = settings or IngestionSettings()
        self._index_writer = index_writer_callback

    def ingest_document(self, raw: RawDocument) -> IngestionResult:
        """
        Ingest a single document through the full pipeline.

        Stages:
        1. Parse (source-specific structural extraction)
        2. Normalize (text cleanup, UUID, metadata tagging)
        3. Chunk (section-aware splitting)
        4. Index writes (if callback configured)
        5. Audit event emission

        Hard-fails on validation, metadata, or governance errors.
        """
        correlation_id = get_correlation_id() or generate_correlation_id()
        set_correlation_id(correlation_id)

        try:
            # Stage 1: Source-specific parsing
            parsed_raw = self._apply_parser(raw)

            # Stage 2: Normalize (governance checkpoint fires inside)
            normalized = self._normalizer.normalize(parsed_raw)

            # Stage 3: Chunk (governance checkpoint fires inside)
            chunks = self._chunker.chunk(normalized)
            chunk_list = list(chunks)

            # Stage 4: Index writes (if configured)
            if self._index_writer and chunk_list:
                try:
                    self._index_writer(normalized, chunk_list)
                except Exception as idx_err:
                    logger.error(
                        "indexing_callback_failed",
                        doc_id=normalized.doc_id,
                        error=str(idx_err),
                    )
                    # Index failure does NOT fail the ingestion — document is still normalized
                    # and chunked. Index retry can happen separately.

            # Audit: success
            self._emit_audit_event(
                principal_id="ingestion-pipeline",
                action=AuditAction.INGESTION_COMPLETE,
                resource=f"DOC:{normalized.doc_id}",
                decision=AuditDecision.ALLOW,
                metadata={
                    "doc_id": normalized.doc_id,
                    "external_id": raw.external_id,
                    "source_system": raw.source_system,
                    "chunks_created": len(chunk_list),
                    "domain_tag": normalized.metadata.domain_tag.value,
                    "sensitivity": normalized.metadata.sensitivity_level.value,
                },
                correlation_id=correlation_id,
            )

            logger.info(
                "ingestion_complete",
                doc_id=normalized.doc_id,
                external_id=raw.external_id,
                chunks=len(chunk_list),
            )

            return IngestionResult(
                doc_id=normalized.doc_id,
                external_id=raw.external_id,
                source_system=raw.source_system,
                status="SUCCESS",
                chunks_created=len(chunk_list),
                domain_tag=normalized.metadata.domain_tag.value,
                sensitivity_level=normalized.metadata.sensitivity_level.value,
            )

        except Exception as exc:
            # Audit: failure
            self._emit_audit_event(
                principal_id="ingestion-pipeline",
                action=AuditAction.INGESTION_COMPLETE,
                resource=f"DOC:{raw.external_id}",
                decision=AuditDecision.ERROR,
                metadata={
                    "external_id": raw.external_id,
                    "source_system": raw.source_system,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                correlation_id=correlation_id,
            )

            logger.error(
                "ingestion_failed",
                external_id=raw.external_id,
                source_system=raw.source_system,
                error=str(exc),
            )

            return IngestionResult(
                doc_id="",
                external_id=raw.external_id,
                source_system=raw.source_system,
                status="FAILED",
                error=str(exc),
            )

    def ingest_batch(self, documents: list[RawDocument]) -> BatchIngestionResult:
        """
        Ingest a batch of documents.

        Each document is processed independently — a failure in one document
        does NOT halt the batch. All results are collected and returned.
        """
        batch_id = str(uuid.uuid4())
        started_at = datetime.now(tz=timezone.utc)
        results: list[IngestionResult] = []

        logger.info(
            "batch_ingestion_start",
            batch_id=batch_id,
            total_documents=len(documents),
        )

        for i, raw in enumerate(documents):
            logger.info(
                "batch_ingestion_progress",
                batch_id=batch_id,
                doc_index=i + 1,
                total=len(documents),
                external_id=raw.external_id,
            )
            result = self.ingest_document(raw)
            results.append(result)

        completed_at = datetime.now(tz=timezone.utc)
        succeeded = [r for r in results if r.status == "SUCCESS"]
        failed = [r for r in results if r.status == "FAILED"]

        batch_result = BatchIngestionResult(
            batch_id=batch_id,
            total_submitted=len(documents),
            total_succeeded=len(succeeded),
            total_failed=len(failed),
            total_chunks=sum(r.chunks_created for r in results),
            results=results,
            started_at=started_at,
            completed_at=completed_at,
        )

        logger.info(
            "batch_ingestion_complete",
            batch_id=batch_id,
            total_submitted=batch_result.total_submitted,
            total_succeeded=batch_result.total_succeeded,
            total_failed=batch_result.total_failed,
            total_chunks=batch_result.total_chunks,
            duration_seconds=(completed_at - started_at).total_seconds(),
        )

        return batch_result

    def _apply_parser(self, raw: RawDocument) -> RawDocument:
        """
        Apply source-specific parser if available.

        Parsers restructure the body text with section markers but do NOT
        modify metadata. If no parser is found, the document passes through
        unmodified.
        """
        parser = self._parser_registry.get_parser_for_source_system(
            raw.source_system
        )

        if parser is None:
            logger.debug(
                "no_parser_found",
                source_system=raw.source_system,
                action="passthrough",
            )
            return raw

        try:
            result = parser.parse(raw.body, raw.title)

            # Construct a new RawDocument with the parsed/assembled body
            return RawDocument(
                external_id=raw.external_id,
                title=result.title or raw.title,
                body=result.assembled_body or raw.body,
                created_at=raw.created_at,
                updated_at=raw.updated_at,
                source_system=raw.source_system,
                raw_metadata=raw.raw_metadata,
            )

        except Exception as exc:
            logger.warning(
                "parser_failed_passthrough",
                source_system=raw.source_system,
                parser=type(parser).__name__,
                error=str(exc),
            )
            # Parser failure is non-fatal — pass through unmodified
            return raw

    def _emit_audit_event(
        self,
        principal_id: str,
        action: AuditAction,
        resource: str,
        decision: AuditDecision,
        metadata: dict[str, Any],
        correlation_id: str = "",
    ) -> None:
        """Emit an audit event for ingestion operations."""
        try:
            event = AuditEvent(
                event_id=str(uuid.uuid4()),
                principal_id=principal_id,
                principal_type="SERVICE",
                action=action,
                resource=resource,
                request_id=correlation_id,
                decision=decision,
                metadata=metadata,
            )
            self._audit.log_event(event)
        except Exception as exc:
            # Audit logging failure should never crash ingestion
            logger.error("audit_emit_failed", error=str(exc))
