import pytest
from unittest.mock import MagicMock

from app.models.answer import (
    ClaimVerificationResult, 
    DraftAnswer, 
    IssueSeverity, 
    VerificationResult, 
    RoutingDecision, 
    RoutingRoute
)
from app.models.evidence import ConsolidatedEvidenceSet, EvidenceChunk, IndexType
from app.models.metadata import DocumentMetadata, DomainTag, SensitivityLevel
from app.verification.scorer import WeightedConfidenceScorer, ThresholdRouter
from app.verification.fallback import FallbackFormatter
from app.verification.rules import ProcurementRuleValidator
from app.verification.verifier import DefaultVerificationLoop

@pytest.fixture
def sample_evidence():
    meta = DocumentMetadata(
        domain_tag=DomainTag.PROCUREMENT,
        sensitivity_level=SensitivityLevel.SECRET,
        version="v1",
        origin="test"
    )
    c1 = EvidenceChunk(doc_id="d1", chunk_id="c1", text="Must file waiver B if cost > 10M", rank=1, index_type=IndexType.KEYWORD, score=0.9, section_path="1.1", metadata=meta)
    return ConsolidatedEvidenceSet(
        query_id="q1",
        user_query="Cost is 15M, what do I do?",
        chunks=[c1],
        indices_used=[IndexType.KEYWORD],
        total_candidates_considered=1,
        max_sensitivity_in_results="SECRET"
    )

def test_scorer_caps_contradictory_claims():
    scorer = WeightedConfidenceScorer()
    
    vr = VerificationResult(
        relevance=1.0, intent_coverage=1.0, evidence_utilization=1.0, claim_similarity=1.0, consistency=0.2, citation_integrity=1.0, domain_rules=1.0,
        claims=[ClaimVerificationResult(claim_id="1", claim_text="test", entailment_score=0.1, contradiction_score=0.9, support_score=0.1, supported=False, blocking=True, issues=["CLAIM_CONTRADICTION"])],
        domain_results=[],
        issues=["CLAIM_CONTRADICTION"],
        issue_categories=["CLAIM_CONTRADICTION"],
        highest_severity=IssueSeverity.BLOCKING,
        iterations=1
    )

    score = scorer.compute(vr)
    assert score <= 0.40, "Contradictory claim was not capped strictly to 0.40"


def test_scorer_caps_unsupported_numeric():
    scorer = WeightedConfidenceScorer()
    vr = VerificationResult(
        relevance=1.0, intent_coverage=1.0, evidence_utilization=1.0, claim_similarity=1.0, consistency=0.5, citation_integrity=1.0, domain_rules=1.0,
        claims=[ClaimVerificationResult(claim_id="1", claim_text="500c", entailment_score=0.1, contradiction_score=0.1, support_score=0.1, supported=False, blocking=True, issues=["NUMERIC_UNSUPPORTED"])],
        domain_results=[],
        issues=["NUMERIC_UNSUPPORTED"],
        issue_categories=["NUMERIC_UNSUPPORTED"],
        highest_severity=IssueSeverity.BLOCKING,
        iterations=1
    )

    score = scorer.compute(vr)
    assert score <= 0.35, "Numeric unsupported did not hard cap scoring limits."


def test_router_blocks_secret_on_fallback():
    router = ThresholdRouter()
    
    vr = VerificationResult(
        relevance=0.8, intent_coverage=0.8, evidence_utilization=0.8, claim_similarity=0.8, consistency=1.0, citation_integrity=1.0, domain_rules=1.0,
        claims=[], domain_results=[], issues=[], issue_categories=[], highest_severity=None, iterations=1
    )
    
    # 0.8 is above public fallback, but secret threshold is 0.93
    decision = router.route(vr, 0.80, "SECRET", ["procurement"])
    
    assert decision.route == RoutingRoute.BLOCKED
    assert "SECRET_FALLBACK_DENIED" in decision.reason_codes


def test_procurement_rule_validator(sample_evidence):
    val = ProcurementRuleValidator()
    
    claims = [
        ClaimVerificationResult(
            claim_id="1",
            claim_text="You must file a waiver immediately without approval.",
            cited_chunk_ids=[],
            entailment_score=0.1,
            contradiction_score=0.0,
            support_score=0.1,
            supported=False,
            blocking=False
        )
    ]
    
    res = val.validate(sample_evidence, claims)
    assert res is not None
    assert res.blocking is True
    assert "UNSUPPORTED_PROCUREMENT_ADVICE_UNCITED" in res.issues
    assert res.score == 0.0


def test_fallback_formatter_scrubs_synthesis(sample_evidence):
    formatter = FallbackFormatter()
    
    draft = DraftAnswer(query_id="q1", text="I strongly think you should use thermal tiles that hold 2000C [d1:c1].", cited_chunks=["c1"])
    vr = VerificationResult(
        relevance=0.8, intent_coverage=0.8, evidence_utilization=0.8, claim_similarity=0.8, consistency=1.0, citation_integrity=1.0, domain_rules=1.0,
        claims=[], domain_results=[], issues=[], issue_categories=[], highest_severity=None, iterations=1
    )
    
    routing = RoutingDecision(route=RoutingRoute.FALLBACK_PARTIAL, confidence=0.75, threshold_applied=0.8, explanation="decayed", reason_codes=[])

    ans = formatter.format(draft, sample_evidence, vr, routing)
    
    # Should NOT contain hallucinated bounds
    assert "2000C" not in ans.answer_text
    assert "thermal tiles" not in ans.answer_text
    # Should contain exact quotes from evidence
    assert len(ans.evidence_snippets) == 1
    assert "Must file waiver B" in ans.evidence_snippets[0]["text"]
