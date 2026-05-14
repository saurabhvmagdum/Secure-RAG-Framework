"""
Query API Endpoint mapping internal Verification loops to safe DTOs.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.security.auth import get_current_principal
from app.core.correlation import get_correlation_id
from app.core.logging import get_logger
from app.models.answer import RoutingRoute
from app.models.auth import Principal
from app.models.metadata import DomainTag
from app.retrieval.service import HybridRetrievalService
from app.verification.verifier import DefaultVerificationLoop

logger = get_logger(__name__)

router = APIRouter()

# DTOs
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000)
    domain_tags: list[str] | None = Field(default=None)
    max_sensitivity: str | None = Field(default=None)

class SafeSnippet(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    section_path: str

class QueryResponse(BaseModel):
    request_id: str
    correlation_id: str
    route: RoutingRoute
    confidence_score: float
    reason_codes: list[str]
    metric_breakdown: dict[str, float]
    
    # Text is explicitly isolated depending on route
    answer_text: str | None 
    evidence_snippets: list[SafeSnippet]
    citations: list[str]
    
    fallback_explanation: str | None
    blocking_explanation: str | None


# Dependency Injection Stubs (In production, provided via FastAPI app state)
def get_retrieval_service() -> HybridRetrievalService:
    from app.retrieval.service import HybridRetrievalService
    return HybridRetrievalService()

def get_verification_loop() -> DefaultVerificationLoop:
    from app.generation.llm import DeterministicLocalLLMService
    from app.generation.prompts import DefaultPromptBuilder
    from app.verification.verifier import DefaultVerificationLoop
    llm = DeterministicLocalLLMService()
    builder = DefaultPromptBuilder()
    return DefaultVerificationLoop(llm, builder)


@router.post("/", response_model=QueryResponse)
async def execute_query(
    request: QueryRequest,
    principal: Principal = Depends(get_current_principal),
    retriever: HybridRetrievalService = Depends(get_retrieval_service),
    verifier: DefaultVerificationLoop = Depends(get_verification_loop),
) -> QueryResponse:
    """
    Executes a secure tri-index retrieval and passes the result
    into the verification loop before mapping it explicitly to a safe DTO.
    """
    correlation_id = get_correlation_id()
    request_id = str(uuid.uuid4())
    
    logger.info("api_query_received", request_id=request_id, principal_id=principal.principal_id)

    # Note: RBAC checks are executed aggressively within the domain components relying on the `principal` object.
    
    try:
        # 1. Retrieve
        evidence = retriever.search(
            query=request.query,
            principal=principal,
            max_sensitivity=request.max_sensitivity,
            domain_filter=request.domain_tags,
        )

        # 2. Verify and Ground
        verified_answer = verifier.run(
            evidence=evidence,
            max_iterations=3,
            principal_id=principal.principal_id,
            max_sensitivity=request.max_sensitivity or "PUBLIC"
        )

        # 3. Secure DTO Mapping
        route = verified_answer.routing.route
        ans_text = verified_answer.answer_text if route == RoutingRoute.HIGH_CONFIDENCE else None
        
        fallback_exp = verified_answer.routing.explanation if route == RoutingRoute.FALLBACK_PARTIAL else None
        blocking_exp = verified_answer.routing.explanation if route == RoutingRoute.BLOCKED else None

        safe_snippets = [
            SafeSnippet(**snippet) for snippet in verified_answer.evidence_snippets
        ]

        metrics = verified_answer.verification.model_dump()
        metric_breakdown = {
            "relevance": metrics.get("relevance", 0.0),
            "intent_coverage": metrics.get("intent_coverage", 0.0),
            "claim_similarity": metrics.get("claim_similarity", 0.0),
            "consistency": metrics.get("consistency", 0.0),
            "citation_integrity": metrics.get("citation_integrity", 0.0),
            "domain_rules": metrics.get("domain_rules", 0.0),
        }

        # Clear citations if fallback since we present the chunks, not standard generated text tags
        citations = verified_answer.cited_chunks if route == RoutingRoute.HIGH_CONFIDENCE else []

        return QueryResponse(
            request_id=request_id,
            correlation_id=correlation_id,
            route=route,
            confidence_score=verified_answer.routing.confidence,
            reason_codes=verified_answer.routing.reason_codes,
            metric_breakdown=metric_breakdown,
            answer_text=ans_text,
            evidence_snippets=safe_snippets,
            citations=citations,
            fallback_explanation=fallback_exp,
            blocking_explanation=blocking_exp,
        )

    except Exception as e:
        logger.error("api_query_fatal", request_id=request_id, error=str(e))
        # Ensure fail-closed routing mapping without revealing stack traces to user
        raise HTTPException(status_code=500, detail="Internal server error during query processing. Bounded to safe-closed state.")

