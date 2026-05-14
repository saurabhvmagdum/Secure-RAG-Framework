"""
Index Schemas
=============

Typed contracts for the BM25 (keyword) and semantic (vector) index entries.
Each index document references its parent via doc_id and chunk_id, and carries
governed metadata for sensitivity-aware partitioning and access control.

Phase 2: Updated to match the field expectations of the OpenSearch and Qdrant
adapter implementations.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.models.metadata import DocumentMetadata


class SimilarityMetric(str, Enum):
    """Supported similarity metrics for semantic search."""

    COSINE = "cosine"
    DOT_PRODUCT = "dot_product"


class IndexingInfo(BaseModel):
    """Index shard and integrity metadata."""

    shard_id: str = Field(
        default="",
        description="Shard identifier for distributed index partitioning",
    )
    checksum: str = Field(
        default="",
        description="Content checksum (SHA-256) for integrity verification",
    )

    model_config = {"extra": "forbid"}


class KeywordIndexDocument(BaseModel):
    """
    BM25 lexical index entry — stored in OpenSearch.

    Represents a chunk of a document with preprocessed tokens for BM25 scoring.
    Index name encodes sensitivity and domain for partitioned storage.
    """

    chunk_id: str = Field(
        ...,
        min_length=1,
        description="FK → Chunk.chunk_id (used as OpenSearch document _id)",
    )
    doc_id: str = Field(
        ...,
        min_length=1,
        description="FK → NormalizedDocument.doc_id",
    )
    index_name: str = Field(
        default="",
        description="Target OpenSearch index name (isro-rag-kw-{sensitivity}-{domain})",
    )
    text: str = Field(
        ...,
        min_length=1,
        description="Original chunk text for BM25 full-text search",
    )
    tokens: list[str] = Field(
        default_factory=list,
        description="Preprocessed tokens (stop-words removed, stemmed/lemmatized)",
    )
    checksum: str = Field(
        default="",
        description="SHA-256 checksum of chunk text for integrity verification",
    )
    metadata: DocumentMetadata = Field(
        ...,
        description="Governed metadata — propagated from source document",
    )

    model_config = {"extra": "forbid"}


class SemanticIndexDocument(BaseModel):
    """
    Semantic vector index entry — stored in Qdrant.

    Contains the dense embedding produced by the on-prem domain-specific encoder.
    Collection name encodes sensitivity level for access-controlled partitioning.
    """

    chunk_id: str = Field(
        ...,
        min_length=1,
        description="FK → Chunk.chunk_id",
    )
    doc_id: str = Field(
        ...,
        min_length=1,
        description="FK → NormalizedDocument.doc_id",
    )
    collection_name: str = Field(
        default="",
        description="Target Qdrant collection (isro-rag-sem-{sensitivity})",
    )
    embedding: list[float] = Field(
        ...,
        description="Dense embedding vector from on-prem domain-specific encoder",
    )
    embedding_model_id: str = Field(
        ...,
        min_length=1,
        description='Model identifier for provenance, e.g. "isro-domain-encoder-v1"',
    )
    similarity_metric: SimilarityMetric = Field(
        default=SimilarityMetric.COSINE,
        description="Similarity metric for nearest-neighbor search",
    )
    metadata: DocumentMetadata = Field(
        ...,
        description="Governed metadata — propagated from source document",
    )

    model_config = {"extra": "forbid"}
