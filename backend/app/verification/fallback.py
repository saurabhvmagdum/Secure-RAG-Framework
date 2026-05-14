"""
Fallback Response Handling
==========================

Cleans output bound for UI minimizing hallucinated bounds providing only explicit
chunks and an explaining summary on why the operation decayed.
"""

from __future__ import annotations

from app.models.answer import VerifiedAnswer, DraftAnswer, VerificationResult, RoutingDecision, RoutingRoute
from app.models.evidence import ConsolidatedEvidenceSet


class FallbackFormatter:
    """
    Cleans untrusted synthesized text replacing it with purely extracted quotes.
    """

    def format(
        self,
        draft: DraftAnswer,
        evidence: ConsolidatedEvidenceSet,
        verification: VerificationResult,
        routing: RoutingDecision
    ) -> VerifiedAnswer:

        # Extract top snippets
        snippets = []
        # Fallback snippet rendering is explicitly mapped to cited or just top chunks
        chunks_to_bind = [c for c in evidence.chunks if c.chunk_id in draft.cited_chunks]
        if not chunks_to_bind:
            chunks_to_bind = evidence.chunks[:3] # Supply generic relevance if no citations

        for c in chunks_to_bind:
            snippets.append({
                "chunk_id": c.chunk_id,
                "text": c.text,
                "doc_id": c.doc_id,
                "section_path": c.section_path
            })

        answer_text = ""
        
        if routing.route == RoutingRoute.BLOCKED:
            answer_text = "I cannot provide an answer based on strictly verified evidence. The results failed verification standards."
        elif routing.route == RoutingRoute.FALLBACK_PARTIAL:
            answer_text = (
                "A direct synthesized answer could not be confidently verified. "
                "The following excerpts from verified documents may contain the information:"
            )
        else:
            answer_text = draft.text

        return VerifiedAnswer(
            query_id=evidence.query_id,
            answer_text=answer_text,
            cited_chunks=[s["chunk_id"] for s in snippets] if routing.route != RoutingRoute.HIGH_CONFIDENCE else draft.cited_chunks,
            verification=verification,
            routing=routing,
            evidence_snippets=snippets if routing.route != RoutingRoute.HIGH_CONFIDENCE else []
        )
