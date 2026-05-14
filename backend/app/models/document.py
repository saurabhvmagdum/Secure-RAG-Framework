"""
Document Schemas
================

Typed contracts for the document lifecycle:
    RawDocument → NormalizedDocument → Chunk

Each stage preserves provenance and enforces governed metadata propagation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.metadata import DocumentMetadata


class RawDocument(BaseModel):
    """
    Ingestion input — as received from source systems.

    Contains unvalidated raw_metadata that must be processed by the
    MetadataTagger and ClassificationEngine before becoming governed metadata.
    """

    external_id: str = Field(
        ...,
        min_length=1,
        description="Source system's document identifier",
    )
    title: str = Field(
        ...,
        min_length=1,
        description="Document title",
    )
    body: str = Field(
        ...,
        description="Full original text content",
    )
    created_at: datetime = Field(
        ...,
        description="Document creation timestamp from source",
    )
    updated_at: datetime = Field(
        ...,
        description="Last modification timestamp from source",
    )
    source_system: str = Field(
        ...,
        min_length=1,
        description='Source system identifier, e.g. "EDMS", "TelemetryDB"',
    )
    raw_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Unvalidated metadata from source — will be processed through "
            "governance-approved tagging pipeline. NOT passed through directly."
        ),
    )

    model_config = {"extra": "forbid"}


class NormalizedDocument(BaseModel):
    """
    Post-normalization document with stable ID and governed metadata.

    The doc_id is a stable UUID that serves as the foreign key across all indices.
    Metadata has been validated against the governance schema.
    """

    doc_id: str = Field(
        ...,
        min_length=1,
        description="Stable UUID — primary key across all indices",
    )
    title: str = Field(
        ...,
        min_length=1,
        description="Normalized document title",
    )
    body: str = Field(
        ...,
        description="Full normalized text content",
    )
    created_at: datetime = Field(
        ...,
        description="Document creation timestamp",
    )
    updated_at: datetime = Field(
        ...,
        description="Last modification timestamp",
    )
    source_system: str = Field(
        ...,
        min_length=1,
        description="Source system identifier",
    )
    metadata: DocumentMetadata = Field(
        ...,
        description="Governed metadata — exactly 4 approved fields",
    )

    model_config = {"extra": "forbid"}


class Chunk(BaseModel):
    """
    Text chunk derived from a NormalizedDocument.

    Chunks are the atomic unit of retrieval. Each chunk:
    - References its parent document via doc_id
    - Has its own unique chunk_id
    - Preserves section_path for traceability
    - Propagates governed metadata from the parent document
    """

    doc_id: str = Field(
        ...,
        min_length=1,
        description="FK → NormalizedDocument.doc_id",
    )
    chunk_id: str = Field(
        ...,
        min_length=1,
        description="Unique chunk identifier",
    )
    section_path: str = Field(
        default="",
        description='Structural path, e.g. "Chapter 3 > Section 3.2"',
    )
    text: str = Field(
        ...,
        min_length=1,
        description="Chunk text content",
    )
    char_count: int = Field(
        default=0,
        ge=0,
        description="Character count of the chunk text",
    )
    token_count: int = Field(
        default=0,
        ge=0,
        description="Approximate token count for the chunk",
    )
    chunk_index: int = Field(
        default=0,
        ge=0,
        description="Position of this chunk within the parent document",
    )
    metadata: DocumentMetadata = Field(
        ...,
        description="Propagated governed metadata from parent NormalizedDocument",
    )

    model_config = {"extra": "forbid"}
