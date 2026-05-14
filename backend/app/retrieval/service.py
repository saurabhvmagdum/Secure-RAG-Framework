"""
Hybrid Retrieval Orchestrator
=============================

Primary service for the retrieval pipeline.
Executes normalized queries across keyword, semantic, and graph indices
in parallel (conceptually), handles graceful degradation if index falls over,
fuses into a single evidence set using RRF, and applies reranking.

Emits `RETRIEVAL_COMPLETE` audit trail entry.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.audit.logger import AuditLogger, FileAuditLogger
from app.audit.models import AuditAction, AuditDecision, AuditEvent, AuditEvidenceContext
from app.core.correlation import add_sub_correlation_id, get_correlation_id
from app.core.exceptions import AuthorizationError, RetrievalError
from app.core.logging import get_logger
from app.models.auth import Principal
from app.models.evidence import ConsolidatedEvidenceSet, EvidenceChunk
from app.reranking.reranker import ExplainableCrossEncoderReranker, Reranker
from app.retrieval.fusion import EvidenceFusion, RecipRankFusion
from app.retrieval.graph import GraphRetriever, Neo4jGraphRetriever
from app.retrieval.keyword import KeywordRetriever, OpenSearchKeywordRetriever
from app.retrieval.query import QueryNormalizer
from app.retrieval.semantic import QdrantSemanticRetriever, SemanticRetriever

logger = get_logger(__name__)


class HybridRetrievalService:
    """
    Coordinates end-to-end evidence gathering.
    Guarantees isolation of retrieval sources: failure in OpenSearch
    does NOT crash Qdrant retrieval, maximizing evidence delivery probability.
    """

    def __init__(
        self,
        keyword_retriever: KeywordRetriever | None = None,
        semantic_retriever: SemanticRetriever | None = None,
        graph_retriever: GraphRetriever | None = None,
        fusion_engine: EvidenceFusion | None = None,
        reranker: Reranker | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self._keyword = keyword_retriever or OpenSearchKeywordRetriever()
        self._semantic = semantic_retriever or QdrantSemanticRetriever()
        self._graph = graph_retriever or Neo4jGraphRetriever()
        self._fusion = fusion_engine or RecipRankFusion()
        self._reranker = reranker or ExplainableCrossEncoderReranker()
        self._audit = audit_logger or FileAuditLogger()

    def search(
        self,
        query: str,
        principal: Principal,
        max_sensitivity: str | None = None,
        domain_filter: list[str] | None = None,
        k_fetch: int = 30,
        k_final: int = 10,
    ) -> ConsolidatedEvidenceSet:
        """
        Execute full Multi-Index Retrieval pipeline.
        
        Args:
            query: Raw user query string.
            principal: The user/agent making the request (for RBAC constraints).
            max_sensitivity: Upper boundary for evidence.
            domain_filter: Restriction list to specific knowledge branches.
            k_fetch: Amount of chunks to procure dynamically from each index cache.
            k_final: Trim size representing final fused & reranked context.
        """
        correlation_id = get_correlation_id()
        query_id = str(uuid.uuid4())
        add_sub_correlation_id(query_id)

        # 1. Normalize Query
        n_query = QueryNormalizer.normalize(query)

        kw_evidence: list[EvidenceChunk] = []
        sem_evidence: list[EvidenceChunk] = []
        gr_evidence: list[EvidenceChunk] = []

        logger.info(
            "hybrid_retrieval_start",
            query_id=query_id,
            principal_id=principal.principal_id,
            normalized_query_len=len(n_query),
        )

        # 2. Parallel/Sequential Safe-Fail Retrieval
        try:
            kw_evidence = self._keyword.retrieve(
                query=n_query,
                principal=principal,
                top_k=k_fetch,
                domain_filter=domain_filter,
                max_sensitivity=max_sensitivity
            )
        except RetrievalError as re:
            logger.warning("hybrid_retrieval_degradation", index="keyword", error=str(re))

        try:
            sem_evidence = self._semantic.retrieve(
                query=n_query,
                principal=principal,
                top_k=k_fetch,
                domain_filter=domain_filter,
                max_sensitivity=max_sensitivity,
                similarity_threshold=0.60
            )
        except RetrievalError as re:
            logger.warning("hybrid_retrieval_degradation", index="semantic", error=str(re))

        try:
            gr_evidence = self._graph.retrieve(
                query=n_query,
                principal=principal,
                top_k=k_fetch,
                max_hops=2,
                domain_filter=domain_filter,
                max_sensitivity=max_sensitivity
            )
        except RetrievalError as re:
            logger.warning("hybrid_retrieval_degradation", index="graph", error=str(re))

        # Check total destruction threshold
        if not (kw_evidence or sem_evidence or gr_evidence):
            logger.error("hybrid_retrieval_zero_evidence", query_id=query_id)
            self._emit_audit(query_id, principal, n_query, max_sensitivity, [], AuditDecision.ERROR)
            # Empty fusion continues securely and passes empty result to LLM cleanly
            
        # 3. Fuse Evidence Streams
        consolidated = self._fusion.fuse(
            query_id=query_id,
            user_query=n_query,
            keyword_evidence=kw_evidence,
            semantic_evidence=sem_evidence,
            graph_evidence=gr_evidence,
            top_k=k_fetch # Keep fetched pool large before rerank
        )

        # 4. Rerank
        final_evidence = self._reranker.rerank(
            evidence=consolidated,
            top_k=k_final,
            diversity_lambda=0.5
        )

        self._emit_audit(
            query_id=query_id, 
            principal=principal, 
            n_query=n_query, 
            max_sensitivity=max_sensitivity, 
            final_evidence=final_evidence.chunks,
            decision=AuditDecision.ALLOW
        )

        return final_evidence

    def _emit_audit(
        self,
        query_id: str,
        principal: Principal,
        query_text: str,
        max_sensitivity: str | None,
        final_evidence: list[EvidenceChunk],
        decision: AuditDecision
    ) -> None:
        
        try:
            extracted_ids = [c.doc_id for c in final_evidence]
            indices_used = list(set([c.index_type.value for c in final_evidence]))
            
            event = AuditEvent(
                event_id=str(uuid.uuid4()),
                principal_id=principal.principal_id,
                principal_type=principal.type.value,
                action=AuditAction.RETRIEVAL_COMPLETE,
                resource="RAG_PIPELINE",
                request_id=get_correlation_id(),
                decision=decision,
                query={
                    "text": query_text,
                    "sensitivity_max": max_sensitivity or "PUBLIC",
                },
                evidence=AuditEvidenceContext(
                    doc_ids=extracted_ids,
                    indices_used=indices_used,
                    chunk_count=len(final_evidence)
                ),
                metadata={"query_id": query_id}
            )
            
            self._audit.log_event(event)

        except Exception as e:
            logger.error("retrieval_audit_emission_failed", error=str(e))
