"""
Semantic Retriever Protocol & Adapter
=============================================

Dense vector similarity retrieval from Qdrant.
Uses on-prem embedding model for query vectorization.

Phase 3: Implements QdrantSemanticRetriever adapter mapping
security bounds to Qdrant Filter objects.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.core.exceptions import RetrievalError
from app.core.logging import get_logger
from app.models.auth import Principal
from app.models.evidence import EvidenceChunk, IndexType
from app.models.metadata import DomainTag, SensitivityLevel, DocumentMetadata
from app.utils.circuit_breaker import CircuitBreaker

logger = get_logger(__name__)


@runtime_checkable
class SemanticRetriever(Protocol):
    """
    Protocol for semantic vector retrieval.
    """

    def retrieve(
        self,
        query: str,
        principal: Principal,
        top_k: int = 20,
        domain_filter: list[str] | None = None,
        max_sensitivity: str | None = None,
        similarity_threshold: float = 0.0,
    ) -> list[EvidenceChunk]:
        """
        Retrieve top-k evidence chunks using semantic similarity.
        """
        ...


class QdrantSemanticRetriever:
    """
    Qdrant adapter for dense semantic retrieval.

    Generates the query embedding using the configured EmbeddingService,
    then queries Qdrant with payload filters for RBAC enforcement.
    """

    def __init__(
        self,
        qdrant_client: Any | None = None,
        embedding_service: Any | None = None,
        vector_size: int = 768,
    ) -> None:
        self._client = qdrant_client
        self._embedder = embedding_service
        self._vector_size = vector_size
        self._circuit_breaker = CircuitBreaker(
            service_name="qdrant_retrieval",
            failure_threshold=3,
            recovery_timeout_seconds=30.0,
        )

    def retrieve(
        self,
        query: str,
        principal: Principal,
        top_k: int = 20,
        domain_filter: list[str] | None = None,
        max_sensitivity: str | None = None,
        similarity_threshold: float = 0.0,
    ) -> list[EvidenceChunk]:
        """
        Run similarity search against the semantic index.
        """
        logger.info(
            "semantic_retrieval_started",
            principal_id=principal.principal_id,
            top_k=top_k,
            domains=domain_filter,
            max_sensitivity=max_sensitivity,
        )

        # 1. Embed query (using on-prem embedding model)
        query_vector = self._embed_query(query)

        if self._client is None:
            # Dry-run stub
            logger.debug("semantic_retriever_dry_run_stub", query=query)
            return []

        try:
            return self._circuit_breaker.call(
                self._execute_search, 
                query_vector, 
                top_k, 
                domain_filter, 
                max_sensitivity, 
                similarity_threshold
            )
        except Exception as exc:
            logger.error("semantic_retrieval_failed", error=str(exc))
            raise RetrievalError(
                message=f"Qdrant retrieval failed: {exc}",
                index_type="semantic",
            ) from exc

    def _embed_query(self, query: str) -> list[float]:
        """Vectorize query using the embedding service."""
        if self._embedder is not None:
            return self._embedder.embed(query)
        logger.debug("semantic_query_embedding_placeholder", query_len=len(query))
        return [0.0] * self._vector_size

    def _execute_search(
        self,
        query_vector: list[float],
        top_k: int,
        domain_filter: list[str] | None,
        max_sensitivity: str | None,
        similarity_threshold: float,
    ) -> list[EvidenceChunk]:
        """Constructs Qdrant filters and fires the Search API."""
        
        # Determine allowed sensitivities for cross-collection queries
        from qdrant_client.http import models as grpc_models
        
        must_conditions = []
        if domain_filter:
            must_conditions.append(
                grpc_models.FieldCondition(
                    key="domain_tag",
                    match=grpc_models.MatchAny(any=domain_filter)
                )
            )

        if max_sensitivity:
            allowed_levels = self._resolve_allowed_sensitivities(max_sensitivity)
            must_conditions.append(
                grpc_models.FieldCondition(
                    key="sensitivity_level",
                    match=grpc_models.MatchAny(any=allowed_levels)
                )
            )

        qdrant_filter = None
        if must_conditions:
            qdrant_filter = grpc_models.Filter(must=must_conditions)

        # We assume points are spread across partitioned collections based on sensitivity
        # For simplicity, if client supports multi-collection search we query "isro-rag-sem-*"
        # or iterate over eligible collections. Assume unified search helper for now.
        search_result = self._client.search(
            collection_name="isro-rag-sem-*",  
            query_vector=query_vector,
            query_filter=qdrant_filter,
            limit=top_k,
            score_threshold=similarity_threshold
        )

        results: list[EvidenceChunk] = []
        for rank, point in enumerate(search_result):
            payload = point.payload or {}
            
            metadata_dict = {
                "domain_tag": DomainTag(payload.get("domain_tag", "general")),
                "sensitivity_level": SensitivityLevel(payload.get("sensitivity_level", "PUBLIC")),
                "version": payload.get("version", "1.0"),
                "origin": payload.get("origin", "unknown"),
            }
            
            chunk = EvidenceChunk(
                doc_id=payload.get("doc_id", "unknown"),
                chunk_id=payload.get("chunk_id", "unknown"),
                text=payload.get("text_chunk", ""), # Requires Qdrant payload to include the text chunk
                rank=rank,
                index_type=IndexType.SEMANTIC,
                score=float(point.score),
                section_path=payload.get("section_path", ""),
                metadata=DocumentMetadata(**metadata_dict),
            )
            results.append(chunk)

        return results

    def _resolve_allowed_sensitivities(self, max_sensitivity: str) -> list[str]:
        """Resolves ordinal limit to list of discrete values."""
        try:
            target = SensitivityLevel(max_sensitivity)
            return [
                lvl.value for lvl in SensitivityLevel 
                if lvl.numeric_level <= target.numeric_level
            ]
        except ValueError:
            return [SensitivityLevel.PUBLIC.value]
