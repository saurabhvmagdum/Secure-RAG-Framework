"""
Indexing package — Index writer interfaces and adapters for BM25 (OpenSearch),
semantic vectors (Qdrant), and knowledge graph (Neo4j).

Includes the IndexingOrchestrator for coordinating tri-index writes.
"""

from app.indexing.keyword import KeywordIndexWriter, OpenSearchKeywordIndexWriter
from app.indexing.semantic import SemanticIndexWriter, QdrantSemanticIndexWriter
from app.indexing.graph import GraphIndexWriter, Neo4jGraphIndexWriter
from app.indexing.orchestrator import IndexingOrchestrator, TriIndexWriteResult

__all__ = [
    "KeywordIndexWriter",
    "OpenSearchKeywordIndexWriter",
    "SemanticIndexWriter",
    "QdrantSemanticIndexWriter",
    "GraphIndexWriter",
    "Neo4jGraphIndexWriter",
    "IndexingOrchestrator",
    "TriIndexWriteResult",
]
