"""
Keyword Retriever Protocol & Adapter
====================================

BM25 lexical retrieval from OpenSearch.
Results are sensitivity-filtered based on the requesting principal's clearance.

Phase 3: Implements the OpenSearchKeywordRetriever adapter with
governance policy filtering (max sensitivity, domain tags) and 
graceful degradation via circuit breaker.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol, runtime_checkable

from app.core.exceptions import RetrievalError
from app.core.logging import get_logger
from app.models.auth import Principal
from app.models.evidence import EvidenceChunk, IndexType
from app.models.metadata import DomainTag, SensitivityLevel, DocumentMetadata
from app.utils.circuit_breaker import CircuitBreaker

logger = get_logger(__name__)


@runtime_checkable
class KeywordRetriever(Protocol):
    """
    Protocol for BM25 lexical retrieval.
    """

    def retrieve(
        self,
        query: str,
        principal: Principal,
        top_k: int = 20,
        domain_filter: list[str] | None = None,
        max_sensitivity: str | None = None,
    ) -> list[EvidenceChunk]:
        """
        Retrieve top-k evidence chunks using BM25 scoring.
        """
        ...


class OpenSearchKeywordRetriever:
    """
    OpenSearch adapter for BM25 lexical retrieval.

    Enforces sensitivity constraints by mapping the principal's max boundary
    into OpenSearch terms queries on the `sensitivity_level` and `domain_tag` fields.
    """

    def __init__(
        self,
        opensearch_client: Any | None = None,
    ) -> None:
        self._client = opensearch_client
        self._circuit_breaker = CircuitBreaker(
            service_name="opensearch_retrieval",
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
    ) -> list[EvidenceChunk]:
        """
        Execute a multi-match BM25 query against OpenSearch indices.
        Throws RetrievalError wrapped via the circuit breaker if the DB is down.
        """
        logger.info(
            "keyword_retrieval_started",
            principal_id=principal.principal_id,
            top_k=top_k,
            domains=domain_filter,
            max_sensitivity=max_sensitivity,
        )

        if self._client is None:
            # Dry-run stub
            logger.debug("keyword_retriever_dry_run_stub", query=query)
            return []

        try:
            return self._circuit_breaker.call(
                self._execute_search, query, top_k, domain_filter, max_sensitivity
            )
        except Exception as exc:
            logger.error("keyword_retrieval_failed", error=str(exc))
            raise RetrievalError(
                message=f"OpenSearch retrieval failed: {exc}",
                index_type="keyword",
                context={"query_len": len(query)},
            ) from exc

    def _execute_search(
        self,
        query: str,
        top_k: int,
        domain_filter: list[str] | None,
        max_sensitivity: str | None,
    ) -> list[EvidenceChunk]:
        """
        Private method to construct and execute the OpenSearch DSL query.
        """
        # Build wildcard index pattern (exclude SECRET from keyword index automatically based on mapping)
        # e.g., isro-rag-kw-*
        index_pattern = "isro-rag-kw-*"

        # Build bool filter query for governance
        must_clauses: list[dict[str, Any]] = [
            {"multi_match": {"query": query, "fields": ["text^2", "tokens"]}}
        ]
        
        filter_clauses: list[dict[str, Any]] = []

        if domain_filter:
            filter_clauses.append({"terms": {"domain_tag": domain_filter}})

        # Limit sensitivity level (OpenSearch requires exact string match, we can use terms for allowed levels)
        if max_sensitivity:
            # Suppose max_sensitivity = INTERNAL. Allowed: PUBLIC, INTERNAL. 
            # SECRET is inherently missing from the KW index, but we explicitly filter.
            allowed_levels = self._resolve_allowed_sensitivities(max_sensitivity)
            filter_clauses.append({"terms": {"sensitivity_level": allowed_levels}})

        es_query = {
            "size": top_k,
            "query": {
                "bool": {
                    "must": must_clauses,
                    "filter": filter_clauses
                }
            }
        }

        # Simulated response if client is mocked (mostly for robust fallback in phase 3 dev)
        response = self._client.search(index=index_pattern, body=es_query)
        
        results: list[EvidenceChunk] = []
        for rank, hit in enumerate(response.get("hits", {}).get("hits", [])):
            source = hit["_source"]
            metadata_dict = {
                "domain_tag": DomainTag(source.get("domain_tag", "general")),
                "sensitivity_level": SensitivityLevel(source.get("sensitivity_level", "PUBLIC")),
                "version": source.get("version", "1.0"),
                "origin": source.get("origin", "unknown"),
            }
            
            chunk = EvidenceChunk(
                doc_id=source["doc_id"],
                chunk_id=source["chunk_id"],
                text=source["text"],
                rank=rank,
                index_type=IndexType.KEYWORD,
                score=float(hit["_score"]),
                section_path=source.get("section_path", ""),
                metadata=DocumentMetadata(**metadata_dict),
            )
            results.append(chunk)

        return results

    def _resolve_allowed_sensitivities(self, max_sensitivity: str) -> list[str]:
        """
        Resolves a maximum sensitivity level string into a list of allowed strings.
        Requires ordinal ranking from the SensitivityLevel enum.
        """
        try:
            target = SensitivityLevel(max_sensitivity)
            return [
                lvl.value for lvl in SensitivityLevel 
                if lvl.numeric_level <= target.numeric_level
            ]
        except ValueError:
            # Fallback fail-closed to PUBLIC
            return [SensitivityLevel.PUBLIC.value]
