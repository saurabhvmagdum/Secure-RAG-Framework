"""
Ingestion Endpoints
====================

API endpoints for document ingestion:
- POST /ingest — Ingest a single document
- POST /ingest/batch — Ingest a batch of documents

All endpoints require authentication and emit audit events.
Governance checkpoints fire at normalization and chunking stages.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.correlation import get_correlation_id
from app.core.logging import get_logger
from app.indexing.orchestrator import IndexingOrchestrator
from app.ingestion.pipeline import (
    BatchIngestionResult,
    IngestionPipeline,
    IngestionResult,
)
from app.models.auth import Principal
from app.models.document import RawDocument
from app.security.auth import get_current_principal

logger = get_logger(__name__)
router = APIRouter()


# ── Request / Response Models ───────────────────────────────────────────────


class IngestDocumentRequest(BaseModel):
    """Single document ingestion request."""

    external_id: str = Field(..., min_length=1, description="Source document ID")
    title: str = Field(..., min_length=1, description="Document title")
    body: str = Field(..., min_length=1, description="Full document text")
    created_at: datetime = Field(..., description="Document creation time")
    updated_at: datetime = Field(..., description="Last modification time")
    source_system: str = Field(..., min_length=1, description="Source system ID")
    raw_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Unvalidated source metadata",
    )

    model_config = {"extra": "forbid"}


class IngestDocumentResponse(BaseModel):
    """Single document ingestion response."""

    doc_id: str
    external_id: str
    source_system: str
    status: str
    chunks_created: int
    domain_tag: str
    sensitivity_level: str
    error: str | None = None
    correlation_id: str


class IngestBatchRequest(BaseModel):
    """Batch document ingestion request."""

    documents: list[IngestDocumentRequest] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of documents to ingest",
    )

    model_config = {"extra": "forbid"}


class IngestBatchResponse(BaseModel):
    """Batch ingestion response."""

    batch_id: str
    total_submitted: int
    total_succeeded: int
    total_failed: int
    total_chunks: int
    results: list[IngestDocumentResponse]


# ── Pipeline Factory ────────────────────────────────────────────────────────


def _create_pipeline() -> IngestionPipeline:
    """Create an ingestion pipeline with tri-index writer callback."""
    orchestrator = IndexingOrchestrator()
    return IngestionPipeline(index_writer_callback=orchestrator)


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=IngestDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a single document",
    description=(
        "Submit a document for ingestion through the full pipeline: "
        "parsing → normalization → chunking → tri-index writes."
    ),
)
async def ingest_document(
    request: IngestDocumentRequest,
    principal: Principal = Depends(get_current_principal),
) -> IngestDocumentResponse:
    """Ingest a single document."""
    correlation_id = get_correlation_id()

    logger.info(
        "api_ingest_single",
        principal_id=principal.principal_id,
        external_id=request.external_id,
        source_system=request.source_system,
        correlation_id=correlation_id,
    )

    # Build RawDocument from request
    raw = RawDocument(
        external_id=request.external_id,
        title=request.title,
        body=request.body,
        created_at=request.created_at,
        updated_at=request.updated_at,
        source_system=request.source_system,
        raw_metadata=request.raw_metadata,
    )

    # Run ingestion pipeline
    pipeline = _create_pipeline()
    result = pipeline.ingest_document(raw)

    if result.status == "FAILED":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Document ingestion failed",
                "external_id": result.external_id,
                "error": result.error,
                "correlation_id": correlation_id,
            },
        )

    return IngestDocumentResponse(
        doc_id=result.doc_id,
        external_id=result.external_id,
        source_system=result.source_system,
        status=result.status,
        chunks_created=result.chunks_created,
        domain_tag=result.domain_tag,
        sensitivity_level=result.sensitivity_level,
        correlation_id=correlation_id,
    )


@router.post(
    "/batch",
    response_model=IngestBatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a batch of documents",
    description=(
        "Submit multiple documents for batch ingestion. Each document is "
        "processed independently — a failure in one does NOT halt the batch."
    ),
)
async def ingest_batch(
    request: IngestBatchRequest,
    principal: Principal = Depends(get_current_principal),
) -> IngestBatchResponse:
    """Ingest a batch of documents."""
    correlation_id = get_correlation_id()

    logger.info(
        "api_ingest_batch",
        principal_id=principal.principal_id,
        total_documents=len(request.documents),
        correlation_id=correlation_id,
    )

    # Build RawDocuments
    raw_docs = [
        RawDocument(
            external_id=doc.external_id,
            title=doc.title,
            body=doc.body,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            source_system=doc.source_system,
            raw_metadata=doc.raw_metadata,
        )
        for doc in request.documents
    ]

    # Run batch ingestion
    pipeline = _create_pipeline()
    batch_result = pipeline.ingest_batch(raw_docs)

    return IngestBatchResponse(
        batch_id=batch_result.batch_id,
        total_submitted=batch_result.total_submitted,
        total_succeeded=batch_result.total_succeeded,
        total_failed=batch_result.total_failed,
        total_chunks=batch_result.total_chunks,
        results=[
            IngestDocumentResponse(
                doc_id=r.doc_id,
                external_id=r.external_id,
                source_system=r.source_system,
                status=r.status,
                chunks_created=r.chunks_created,
                domain_tag=r.domain_tag,
                sensitivity_level=r.sensitivity_level,
                error=r.error,
                correlation_id=correlation_id,
            )
            for r in batch_result.results
        ],
    )
