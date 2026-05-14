"""
Local LLM Service Deterministic Contract Stub
==============================================

Stress tests the verification pipeline heavily by outputting specific explicit errors
to trigger bounded verification actions simulating the exact behavior of local quantized models.
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from app.core.exceptions import GenerationError
from app.core.logging import get_logger
from app.models.answer import DraftAnswer
from app.models.evidence import ConsolidatedEvidenceSet
from app.utils.circuit_breaker import CircuitBreaker

logger = get_logger(__name__)


@runtime_checkable
class LocalLLMService(Protocol):
    def generate(
        self,
        evidence: ConsolidatedEvidenceSet,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> DraftAnswer: ...

    def regenerate_with_feedback(
        self,
        evidence: ConsolidatedEvidenceSet,
        previous_answer: DraftAnswer,
        feedback: str,
    ) -> DraftAnswer: ...


class DeterministicLocalLLMService:
    """
    Simulates output logic of a local model precisely.
    Modes:
        - SUPPORTED_MINIMAL
        - MISSING_CITATIONS
        - PARTIAL_COVERAGE
        - CONTRADICTORY_CLAIM
        - UNSUPPORTED_PROCUREMENT_ADVICE
        - EMPTY_EVIDENCE_DECLINE
    """

    def __init__(self, mode: str = "SUPPORTED_MINIMAL"):
        self.mode = os.getenv("LLM_STRESS_MODE", mode)
        self._circuit_breaker = CircuitBreaker(service_name="llm_inference", failure_threshold=2)
        logger.info("llm_stub_initialized", mode=self.mode)

    def generate(
        self,
        evidence: ConsolidatedEvidenceSet,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> DraftAnswer:

        if not evidence.chunks:
            return self._build_empty(evidence)
        
        return self._circuit_breaker.call(self._route_generation, evidence)

    def _route_generation(self, evidence: ConsolidatedEvidenceSet) -> DraftAnswer:
        c1 = f"[{evidence.chunks[0].doc_id}:{evidence.chunks[0].chunk_id}]" if evidence.chunks else "[missing:error]"

        if self.mode == "SUPPORTED_MINIMAL":
            text = f"The anomaly was caused by thermal expansion limits {c1}."
            return DraftAnswer(query_id=evidence.query_id, text=text, cited_chunks=[evidence.chunks[0].chunk_id])

        elif self.mode == "MISSING_CITATIONS":
            text = "The anomaly was caused by thermal expansion limits but I forgot the tag."
            return DraftAnswer(query_id=evidence.query_id, text=text, cited_chunks=[])

        elif self.mode == "PARTIAL_COVERAGE":
            text = f"I can answer part A {c1}, but I don't know part B."
            return DraftAnswer(query_id=evidence.query_id, text=text, cited_chunks=[evidence.chunks[0].chunk_id])

        elif self.mode == "CONTRADICTORY_CLAIM":
            text = f"The thermal limit is 500C {c1} (even though evidence says 200C)."
            return DraftAnswer(query_id=evidence.query_id, text=text, cited_chunks=[evidence.chunks[0].chunk_id])

        elif self.mode == "UNSUPPORTED_PROCUREMENT_ADVICE":
            text = "You must immediately issue a Category B solicitation waiver (synthetic procedure)."
            return DraftAnswer(query_id=evidence.query_id, text=text, cited_chunks=[])

        return self._build_empty(evidence)

    def regenerate_with_feedback(
        self,
        evidence: ConsolidatedEvidenceSet,
        previous_answer: DraftAnswer,
        feedback: str,
    ) -> DraftAnswer:
        
        logger.info("llm_regenerating", query=evidence.query_id, feedback_snippet=feedback[:50])
        
        # If the feedback says missing citations, we fix it
        if "Missing citations" in feedback or self.mode == "MISSING_CITATIONS":
            c1 = evidence.chunks[0].chunk_id if evidence.chunks else "chk1"
            text = f"I apologize. The anomaly was caused by thermal expansion [{evidence.chunks[0].doc_id}:{c1}]."
            return DraftAnswer(query_id=evidence.query_id, text=text, cited_chunks=[c1])
        
        # If contradiction, standard small LLMs often apologize but repeat or struggle.
        if "Contradiction" in feedback:
            text = "Sorry, I am constrained. The limit is 200C according to my context."
            # Maybe fixed
            return DraftAnswer(query_id=evidence.query_id, text=text, cited_chunks=[evidence.chunks[0].chunk_id])

        # Otherwise just return supported
        return self._route_generation(evidence)

    def _build_empty(self, evidence: ConsolidatedEvidenceSet) -> DraftAnswer:
        return DraftAnswer(
            query_id=evidence.query_id,
            text="I cannot answer this query based on the supplied evidence.",
            cited_chunks=[]
        )
