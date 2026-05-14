"""
Evidence Schemas
================

Typed contracts for evidence objects flowing through the retrieval and
verification pipeline:
    EvidenceChunk — single ranked piece of evidence from any index
    ConsolidatedEvidenceSet — merged evidence set ready for verification/generation
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.models.metadata import DocumentMetadata


class IndexType(str, Enum):
    """Source index from which an evidence chunk was retrieved."""

    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    GRAPH = "graph"


class EvidenceChunk(BaseModel):
    """
    A single piece of evidence retrieved from any index.

    Carries its rank, retrieval score, source index type, and full governed
    metadata for classification-aware downstream processing.
    """

    doc_id: str = Field(
        ...,
        min_length=1,
        description="FK → NormalizedDocument.doc_id",
    )
    chunk_id: str = Field(
        ...,
        min_length=1,
        description="FK → Chunk.chunk_id",
    )
    text: str = Field(
        ...,
        min_length=1,
        description="Evidence text content",
    )
    rank: int = Field(
        ...,
        ge=0,
        description="Rank position in retrieval results (0 = best)",
    )
    index_type: IndexType = Field(
        ...,
        description="Which index produced this evidence",
    )
    score: float = Field(
        ...,
        description="Retrieval score (BM25 score, cosine similarity, or graph relevance)",
    )
    section_path: str = Field(
        default="",
        description="Structural path within the source document",
    )
    metadata: DocumentMetadata = Field(
        ...,
        description="Governed metadata from the source chunk",
    )

    model_config = {"extra": "forbid"}


class ConsolidatedEvidenceSet(BaseModel):
    """
    Merged evidence from all three indices after fusion and reranking.

    This is the primary input to the verification and generation layers.
    Contains the normalized query, all evidence chunks, and retrieval metadata.
    """

    query_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for this query session",
    )
    user_query: str = Field(
        ...,
        min_length=1,
        description="Original (normalized) user query",
    )
    chunks: list[EvidenceChunk] = Field(
        default_factory=list,
        description="Ranked evidence chunks from hybrid retrieval",
    )
    indices_used: list[IndexType] = Field(
        default_factory=lambda: list(IndexType),
        description="Which indices contributed to this evidence set",
    )
    total_candidates_considered: int = Field(
        default=0,
        ge=0,
        description="Total number of candidate chunks before fusion/filtering",
    )
    max_sensitivity_in_results: str = Field(
        default="PUBLIC",
        description="Highest sensitivity level among returned evidence chunks",
    )

    model_config = {"extra": "forbid"}
