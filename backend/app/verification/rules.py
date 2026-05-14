"""
Domain Specific Rule Validation
===============================

Pluggable structure validating nuanced boundaries across varying domains 
where general linguistic overlap fails to prove correctness (e.g. Procurement).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.answer import DraftAnswer, DomainRuleValidationResult, ClaimVerificationResult
from app.models.evidence import ConsolidatedEvidenceSet


@runtime_checkable
class DomainValidator(Protocol):
    def validate(
        self, 
        evidence: ConsolidatedEvidenceSet, 
        claims: list[ClaimVerificationResult]
    ) -> DomainRuleValidationResult | None: ...


class ProcurementRuleValidator:
    """
    Requires exact clause operational rule identifier presence for normative advice.
    """
    
    def validate(
        self, 
        evidence: ConsolidatedEvidenceSet, 
        claims: list[ClaimVerificationResult]
    ) -> DomainRuleValidationResult | None:
        
        # Only trigger if the evidence pool belongs strictly to procurement
        if not any(c.metadata.domain_tag.value == "procurement" for c in evidence.chunks):
            return None

        issues = []
        blocked = False
        
        for claim in claims:
            txt = claim.claim_text.lower()
            if "must" in txt or "waiver" in txt or "procedure" in txt:
                if not claim.cited_chunk_ids:
                    issues.append("UNSUPPORTED_PROCUREMENT_ADVICE_UNCITED")
                    blocked = True
                elif claim.support_score < 0.90:
                    # Normative advice requires explicitly high overlap (exact clause matches)
                    issues.append("PROCEDURAL_ADVICE_MISSING_EXACT_CLAUSE")
                    blocked = True

        passed = not blocked

        return DomainRuleValidationResult(
            domain_tag="procurement",
            score=0.0 if blocked else 1.0,
            passed=passed,
            blocking=blocked,
            issues=issues,
            reason_codes=["PROCEDURE_VIOLATION"] if blocked else []
        )
