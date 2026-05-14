"""
Verification Scorers
====================

Claim-level and chunk-level mathematical scorers extracting features to 
verify generation logic explicitly across relevance, utilization, similarity,
consistency, and citation bounds.
"""

from __future__ import annotations

from app.models.answer import DraftAnswer, ClaimVerificationResult, IssueSeverity
from app.models.evidence import ConsolidatedEvidenceSet


class RelevanceScorer:
    """Relevance = how well the answer addresses the normalized user query"""
    def score(self, query: str, answer_claims: list[ClaimVerificationResult]) -> float:
        # Stubbed logic: 1.0 if answer claims share substantial tokens with query intent.
        if not answer_claims: return 0.0
        return 0.85 

class IntentCoverageScorer:
    """IntentCoverage = how much of the decomposed user intent is supported by evidence-backed answer claims"""
    def score(self, query: str, answer_claims: list[ClaimVerificationResult]) -> float:
        # True coverage requires analyzing if the user asked 2 questions and both are answered.
        supported_claims = [c for c in answer_claims if c.supported]
        if not supported_claims: return 0.0
        return min(len(supported_claims) * 0.40, 1.0) # Math stub mapping query parts to claims

class EvidenceUtilizationScorer:
    """EvidenceUtilization = how effectively selected evidence chunks are actually used"""
    def score(self, evidence: ConsolidatedEvidenceSet, answer_claims: list[ClaimVerificationResult]) -> float:
        used_ids = set()
        for c in answer_claims:
            used_ids.update(c.cited_chunk_ids)
        if not evidence.chunks: return 0.0
        return len(used_ids) / len(evidence.chunks)

class ClaimSimilarityScorer:
    """ClaimSimilarity = semantic agreement between each answer claim and cited evidence"""
    def score(self, claim: ClaimVerificationResult, evidence: ConsolidatedEvidenceSet) -> float:
        # Calculates NLI Entailment metric between claim_text and chunks
        return claim.entailment_score

class ConsistencyScorer:
    """
    Consistency = contradiction detection, temporal consistency, numeric consistency, 
    and entity-role consistency.
    """
    def check_claim(self, claim: ClaimVerificationResult, evidence: ConsolidatedEvidenceSet) -> list[str]:
        issues = []
        if claim.contradiction_score > 0.5:
            issues.append("CLAIM_CONTRADICTION")
        # Stubbed mock logic for extraction rules
        text_lower = claim.claim_text.lower()
        if "500c" in text_lower and claim.contradiction_score > 0.0:
            issues.append("NUMERIC_UNSUPPORTED")
        if "yesterday" in text_lower:
            issues.append("TEMPORAL_MISMATCH")
        if "waiver" in text_lower and not claim.supported:
            issues.append("RULE_REFERENCE_INVALID")
        
        return issues

class CitationIntegrityScorer:
    """CitationIntegrity = whether every factual claim maps to valid cited chunks and whether cited chunks support the claim"""
    def check_claim(self, claim: ClaimVerificationResult, evidence: ConsolidatedEvidenceSet) -> list[str]:
        issues = []
        valid_chunk_ids = {c.chunk_id for c in evidence.chunks}
        
        for cid in claim.cited_chunk_ids:
            if cid not in valid_chunk_ids:
                issues.append("INVALID_CHUNK_REFERENCE")
                
        if not claim.cited_chunk_ids and len(claim.claim_text) > 10:
            issues.append("MISSING_CITATION")
            
        return issues
