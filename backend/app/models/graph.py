"""
Knowledge Graph Schemas
=======================

Typed contracts for Neo4j graph entities: nodes and edges.
Node properties carry governed metadata and provenance tracking.
Edge properties carry extraction confidence, provenance, and method.

Phase 2: Updated to match the field expectations of the Neo4j adapter
and rule-based entity extraction system.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GraphNodeProperties(BaseModel):
    """
    Properties attached to a graph node.

    Carries entity identification, governed metadata, and provenance
    back to source documents/chunks.
    """

    canonical_name: str = Field(
        ...,
        min_length=1,
        description="Canonical name of the entity (deduplicated key)",
    )
    display_name: str = Field(
        ...,
        min_length=1,
        description="Display name for UI rendering",
    )
    entity_type: str = Field(
        ...,
        min_length=1,
        description="Entity type: MISSION, COMPONENT, SYSTEM, PARAMETER, ANOMALY, FACILITY",
    )
    source_doc_ids: list[str] = Field(
        default_factory=list,
        description="List of doc_ids this entity was extracted from",
    )
    source_chunk_ids: list[str] = Field(
        default_factory=list,
        description="List of chunk_ids this entity was extracted from",
    )
    domain_tag: str = Field(
        ...,
        description="Domain classification from controlled vocabulary",
    )
    sensitivity_level: str = Field(
        ...,
        description="Data sensitivity level from classification policy",
    )

    model_config = {"extra": "forbid"}


class GraphNode(BaseModel):
    """
    Knowledge graph node — stored in Neo4j.

    Represents an entity extracted from documents: missions, components,
    systems, parameters, anomalies, facilities, etc.

    node_id is deterministic from entity_type + canonical_name for
    idempotent upserts.
    """

    node_id: str = Field(
        ...,
        min_length=1,
        description="Deterministic UUID5 from entity_type + canonical_name",
    )
    label: str = Field(
        ...,
        min_length=1,
        description="Neo4j node label (entity type)",
    )
    properties: GraphNodeProperties = Field(
        ...,
        description="Entity properties with governed metadata and provenance",
    )

    model_config = {"extra": "forbid"}


class GraphEdgeProperties(BaseModel):
    """
    Properties attached to a graph edge.

    Carries extraction confidence, provenance, and method for auditability.
    """

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Extraction confidence (1.0 = exact pattern match)",
    )
    source_chunk_id: str = Field(
        default="",
        description="FK → Chunk.chunk_id — chunk from which this relation was extracted",
    )
    source_doc_id: str = Field(
        default="",
        description="FK → NormalizedDocument.doc_id",
    )
    extraction_method: str = Field(
        default="rule_based_cooccurrence",
        description="Method used: rule_based_cooccurrence | manual | ml_ner",
    )

    model_config = {"extra": "forbid"}


class GraphEdge(BaseModel):
    """
    Knowledge graph edge — stored in Neo4j.

    Represents a typed relationship between two entities.
    Relation types: USES_COMPONENT, HAS_SYSTEM, HAS_PARAMETER,
    DETECTED_ANOMALY, LAUNCHED_FROM, PART_OF_SYSTEM, etc.

    edge_id is deterministic from source_id + relation + target_id for
    idempotent upserts.
    """

    edge_id: str = Field(
        ...,
        min_length=1,
        description="Deterministic UUID5 from source + relation + target",
    )
    source_node_id: str = Field(
        ...,
        min_length=1,
        description="Source node ID",
    )
    target_node_id: str = Field(
        ...,
        min_length=1,
        description="Target node ID",
    )
    relation_type: str = Field(
        ...,
        min_length=1,
        description="Relationship type (from governance-approved templates)",
    )
    properties: GraphEdgeProperties = Field(
        ...,
        description="Edge properties with confidence and provenance",
    )

    model_config = {"extra": "forbid"}
