"""
Prompt Builder Protocol & Output Formatting
===========================================

Constructs grounded prompts for the on-prem LLM ensuring:
- Strict citation tracking
- Prohibitions on speculative text
- MMR based context packing
- Exposing excluded logs
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.logging import get_logger
from app.models.evidence import ConsolidatedEvidenceSet, EvidenceChunk

logger = get_logger(__name__)


@runtime_checkable
class PromptBuilder(Protocol):
    """Protocol for constructing grounded LLM prompts."""

    def build_generation_prompt(
        self,
        evidence: ConsolidatedEvidenceSet,
        selected_chunks: list[EvidenceChunk],
    ) -> str:
        """Build initial grounded prompt."""
        ...

    def build_regeneration_prompt(
        self,
        evidence: ConsolidatedEvidenceSet,
        selected_chunks: list[EvidenceChunk],
        previous_answer: str,
        feedback: str,
    ) -> str:
        """Build a regeneration prompt highlighting structural feedback."""
        ...

    def select_chunks_for_prompt(
        self,
        evidence: ConsolidatedEvidenceSet,
        max_chunks: int = 10,
    ) -> list[EvidenceChunk]:
        """Pack prompt conditionally keeping coverage."""
        ...


class DefaultPromptBuilder:

    SYSTEM_INSTRUCTION = (
        "You are an ISRO Secure AI Assistant operating in an air-gapped system. "
        "Your task is to answer the query USING ONLY the supplied evidence. "
        "If the evidence does not contain the answer, you must refuse to answer. "
        "Every factual claim you make MUST be followed by the explicit chunk ID bracketed "
        "like [doc_1:chunk_5]. Do not invent metadata. Do not offer external logic."
    )

    def build_generation_prompt(
        self,
        evidence: ConsolidatedEvidenceSet,
        selected_chunks: list[EvidenceChunk],
    ) -> str:
        
        prompt = self.SYSTEM_INSTRUCTION + "\n\n"
        prompt += f"QUERY:\n{evidence.user_query}\n\n"
        prompt += "EVIDENCE:\n"
        
        for c in selected_chunks:
            prompt += f"--- [{c.doc_id}:{c.chunk_id}] ---\n"
            prompt += f"Text: {c.text}\n\n"
            
        prompt += "OUTPUT FORMAT:\n"
        prompt += "Ensure 100% of your statements map back to the bracket tags.\n\n"
        prompt += "ANSWER:\n"
        
        return prompt

    def build_regeneration_prompt(
        self,
        evidence: ConsolidatedEvidenceSet,
        selected_chunks: list[EvidenceChunk],
        previous_answer: str,
        feedback: str,
    ) -> str:
        
        prompt = self.SYSTEM_INSTRUCTION + "\n\n"
        prompt += f"QUERY: {evidence.user_query}\n\n"
        prompt += "PREVIOUS ANSWER (REJECTED BY VERIFICATION VERIFIER):\n"
        prompt += f"{previous_answer}\n\n"
        prompt += f"SYSTEM FEEDBACK THAT MUST BE RESOLVED:\n{feedback}\n\n"
        
        prompt += "EVIDENCE:\n"
        for c in selected_chunks:
            prompt += f"--- [{c.doc_id}:{c.chunk_id}] ---\n"
            prompt += f"Text: {c.text}\n\n"
            
        prompt += "Revise your answer to correct the feedback strictly abiding by evidence.\n"
        prompt += "ANSWER:\n"
        
        return prompt

    def select_chunks_for_prompt(
        self,
        evidence: ConsolidatedEvidenceSet,
        max_chunks: int = 10,
    ) -> list[EvidenceChunk]:
        """
        Packs chunks safely utilizing MMR principles implicitly executed during the 
        fusion and reranking stages prior to this method's execution.
        """
        selected = evidence.chunks[:max_chunks]
        excluded = evidence.chunks[max_chunks:]
        
        logger.debug(
            "context_packing",
            query_id=evidence.query_id,
            total_selected=len(selected),
            total_excluded=len(excluded),
            excluded_ids=[f"{c.doc_id}:{c.chunk_id}" for c in excluded]
        )
        
        return selected

