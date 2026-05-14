"""
Domain Models Package
=====================

All Pydantic schemas used across the ISRO RAG pipeline.
Shared by all layers — no business logic, only typed contracts.
"""

from app.models.metadata import DocumentMetadata, DomainTag, SensitivityLevel
from app.models.document import Chunk, NormalizedDocument, RawDocument
from app.models.index import KeywordIndexDocument, SemanticIndexDocument
from app.models.graph import GraphEdge, GraphEdgeProperties, GraphNode, GraphNodeProperties
from app.models.evidence import ConsolidatedEvidenceSet, EvidenceChunk
from app.models.answer import DraftAnswer, RoutingDecision, VerificationResult, VerifiedAnswer
from app.models.auth import Permission, PermissionAction, Principal, PrincipalType, Role

__all__ = [
    # Metadata
    "DomainTag",
    "SensitivityLevel",
    "DocumentMetadata",
    # Documents
    "RawDocument",
    "NormalizedDocument",
    "Chunk",
    # Index
    "KeywordIndexDocument",
    "SemanticIndexDocument",
    # Graph
    "GraphNode",
    "GraphNodeProperties",
    "GraphEdge",
    "GraphEdgeProperties",
    # Evidence
    "EvidenceChunk",
    "ConsolidatedEvidenceSet",
    # Answer
    "DraftAnswer",
    "VerificationResult",
    "RoutingDecision",
    "VerifiedAnswer",
    # Auth
    "PrincipalType",
    "PermissionAction",
    "Principal",
    "Role",
    "Permission",
]
