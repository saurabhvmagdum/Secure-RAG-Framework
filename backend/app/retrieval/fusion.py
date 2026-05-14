"""
Evidence Fusion Protocol & Logic
================================

Merges and deduplicates evidence from keyword, semantic, and graph retrievers
into a single ConsolidatedEvidenceSet.

Using Reciprocal Rank Fusion (RRF).
Governance checkpoint: retrieval.pre_hybrid_merge
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.logging import get_logger
from app.governance.checkpoint import governance_checkpoint
from app.models.evidence import ConsolidatedEvidenceSet, EvidenceChunk, IndexType

logger = get_logger(__name__)


@runtime_checkable
class EvidenceFusion(Protocol):
    """
    Protocol for evidence consolidation.
    """

    def fuse(
        self,
        query_id: str,
        user_query: str,
        keyword_evidence: list[EvidenceChunk],
        semantic_evidence: list[EvidenceChunk],
        graph_evidence: list[EvidenceChunk],
        top_k: int = 20,
    ) -> ConsolidatedEvidenceSet:
        """
        Fuse evidence from all three retrieval sources.
        """
        ...


class RecipRankFusion:
    """
    Implements Reciprocal Rank Fusion to merge dissimilar index rankings
    into a uniform sorted list while deduplicating exact chunk overlap.
    """

    # Constant applied to ranks in RRF (Standard recommendation is 60)
    RRF_CONSTANT = 60

    @governance_checkpoint("retrieval.pre_hybrid_merge", require_principal=False)
    def fuse(
        self,
        query_id: str,
        user_query: str,
        keyword_evidence: list[EvidenceChunk],
        semantic_evidence: list[EvidenceChunk],
        graph_evidence: list[EvidenceChunk],
        top_k: int = 20,
    ) -> ConsolidatedEvidenceSet:
        
        logger.info(
            "hybrid_fusion_starting",
            query_id=query_id,
            keyword_qty=len(keyword_evidence),
            semantic_qty=len(semantic_evidence),
            graph_qty=len(graph_evidence),
        )

        all_lists = [
            (keyword_evidence, IndexType.KEYWORD),
            (semantic_evidence, IndexType.SEMANTIC),
            (graph_evidence, IndexType.GRAPH),
        ]

        # Keyed by doc_id:chunk_id -> EvidenceChunk dict to preserve highest grade chunk payload
        fused_scores: dict[str, float] = {}
        chunk_map: dict[str, EvidenceChunk] = {}
        indices_used_set: set[IndexType] = set()

        total_candidates = 0

        # RRF Calculation
        for evidence_list, idx_type in all_lists:
            if not evidence_list:
                continue

            indices_used_set.add(idx_type)
            total_candidates += len(evidence_list)
            
            # Sort individual list by its internal rank before scoring
            evidence_list.sort(key=lambda x: x.rank)

            for rank_pos, chunk in enumerate(evidence_list):
                uid = f"{chunk.doc_id}:{chunk.chunk_id}"
                
                # RRF Formula: score = 1 / (k + rank)
                rrf_score = 1.0 / (self.RRF_CONSTANT + (rank_pos + 1))
                
                if uid not in fused_scores:
                    fused_scores[uid] = 0.0
                    chunk_map[uid] = chunk  # Keep the first seen copy of the chunk object
                
                fused_scores[uid] += rrf_score

        # Sorting deduplicated elements by fused score
        ranked_uids = sorted(fused_scores.keys(), key=lambda uid: fused_scores[uid], reverse=True)
        top_uids = ranked_uids[:top_k]

        merged_chunks = []
        max_sensitivity_val = 0
        max_sens_str = "PUBLIC"
        
        for final_rank, uid in enumerate(top_uids):
            chunk = chunk_map[uid]
            # Replace inline rank and score with the hybridized output
            chunk.rank = final_rank
            chunk.score = fused_scores[uid]
            
            # Track max sensitivity present in resulting set
            if chunk.metadata.sensitivity_level.numeric_level > max_sensitivity_val:
                max_sensitivity_val = chunk.metadata.sensitivity_level.numeric_level
                max_sens_str = chunk.metadata.sensitivity_level.value

            merged_chunks.append(chunk)

        set_result = ConsolidatedEvidenceSet(
            query_id=query_id,
            user_query=user_query,
            chunks=merged_chunks,
            indices_used=list(indices_used_set),
            total_candidates_considered=total_candidates,
            max_sensitivity_in_results=max_sens_str,
        )

        logger.info(
            "hybrid_fusion_complete",
            query_id=query_id,
            unique_chunks_kept=len(merged_chunks),
            max_sensitivity=max_sens_str,
        )

        return set_result
