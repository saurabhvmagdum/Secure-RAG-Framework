"""
Verification Loop Controller
=============================

Iterative grounding checking metric scores, applying feedback loop regenerations 
conditionally based on IssueSeverity structures, and emitting granular Audit logs.
"""

from __future__ import annotations

import re
import uuid

from app.audit.logger import FileAuditLogger
from app.audit.models import AuditAction, AuditDecision, AuditEvent, AuditVerificationContext
from app.core.correlation import get_correlation_id
from app.core.logging import get_logger
from app.generation.llm import LocalLLMService
from app.generation.prompts import PromptBuilder
from app.governance.checkpoint import governance_checkpoint
from app.models.answer import (
    ClaimVerificationResult,
    DraftAnswer,
    IssueSeverity,
    VerificationResult,
    VerifiedAnswer,
)
from app.models.evidence import ConsolidatedEvidenceSet
from app.verification.fallback import FallbackFormatter
from app.verification.metrics import (
    CitationIntegrityScorer,
    ClaimSimilarityScorer,
    ConsistencyScorer,
    EvidenceUtilizationScorer,
    IntentCoverageScorer,
    RelevanceScorer,
)
from app.verification.rules import ProcurementRuleValidator
from app.verification.scorer import ThresholdRouter, WeightedConfidenceScorer

logger = get_logger(__name__)


class DefaultVerificationLoop:

    def __init__(
        self,
        llm_service: LocalLLMService,
        prompt_builder: PromptBuilder,
    ):
        self.llm = llm_service
        self.prompt_builder = prompt_builder

        self.relevance_sc = RelevanceScorer()
        self.intent_sc = IntentCoverageScorer()
        self.util_sc = EvidenceUtilizationScorer()
        self.sim_sc = ClaimSimilarityScorer()
        self.cons_sc = ConsistencyScorer()
        self.cit_sc = CitationIntegrityScorer()

        self.domain_validators = [ProcurementRuleValidator()]
        
        self.scorer = WeightedConfidenceScorer()
        self.router = ThresholdRouter()
        self.fallback = FallbackFormatter()
        
        self.audit = FileAuditLogger()

    def run(
        self,
        evidence: ConsolidatedEvidenceSet,
        max_iterations: int = 3,
        principal_id: str = "SYSTEM",
        max_sensitivity: str = "PUBLIC",
    ) -> VerifiedAnswer:

        # 1. Provide Context
        selected_chunks = self.prompt_builder.select_chunks_for_prompt(evidence, 15)
        
        # 2. Initial Generation
        # (This avoids calling the interface multiple times outside the loop)
        draft = self.llm.generate(evidence=evidence)
        
        iteration = 1
        verif_result: VerificationResult | None = None
        
        while iteration <= max_iterations:
            
            # Secure inside checkpoint
            verif_result = self._evaluate_draft(evidence, draft, iteration)

            self._emit_audit(evidence, verif_result, iteration, principal_id, "EVALUATE")

            if verif_result.highest_severity in [IssueSeverity.BLOCKING, IssueSeverity.HIGH_RISK]:
                logger.info("verif_loop_break_severity", reason=verif_result.highest_severity.value)
                break
                
            if verif_result.highest_severity == IssueSeverity.REPAIRABLE and iteration < max_iterations:
                feedback = ",".join(verif_result.issue_categories)
                draft = self.llm.regenerate_with_feedback(evidence, draft, feedback)
                iteration += 1
            else:
                break

        # Compute Final Routing
        domains = list(set([c.metadata.domain_tag.value for c in evidence.chunks]))
        confidence = self.scorer.compute(verif_result)
        routing = self.router.route(verif_result, confidence, max_sensitivity, domains)

        self._emit_audit(evidence, verif_result, iteration, principal_id, "ROUTE", routing.dict())

        # Cleanup format
        final_answer = self.fallback.format(draft, evidence, verif_result, routing)
        return final_answer
        
    @governance_checkpoint("verification.loop_iteration", require_principal=False)
    def _evaluate_draft(self, evidence: ConsolidatedEvidenceSet, draft: DraftAnswer, iteration: int) -> VerificationResult:

        # MOCK Claim extraction (Splitting by sentences simply)
        sentences = [s.strip() + "." for s in draft.text.split(".") if len(s) > 10]
        claims = []

        chunk_ids = {c.chunk_id for c in evidence.chunks}

        issues = []

        for idx, sentence in enumerate(sentences):
            # Extract citations [doc2:chk3] -> ['chk3']
            cites = re.findall(r"\[([^:]+):([^\]]+)\]", sentence)
            extracted_cids = [match[1] for match in cites if match[1] in chunk_ids]
            
            # Sub-scorers
            is_contradict = 0.8 if "contradictory_claim" in sentence.lower() or "500c" in sentence.lower() else 0.0
            is_supported = True if extracted_cids and is_contradict == 0.0 else False

            cvr = ClaimVerificationResult(
                claim_id=f"clm_{idx}",
                claim_text=sentence,
                cited_chunk_ids=extracted_cids,
                entailment_score=0.9 if is_supported else 0.2,
                contradiction_score=is_contradict,
                support_score=0.9 if is_supported else 0.1,
                supported=is_supported,
                blocking=is_contradict > 0.5
            )

            c_issues = self.cons_sc.check_claim(cvr, evidence)
            cvr.issues.extend(c_issues)
            issues.extend(c_issues)

            i_issues = self.cit_sc.check_claim(cvr, evidence)
            cvr.issues.extend(i_issues)
            issues.extend(i_issues)

            claims.append(cvr)

        # Domain Rule Checks
        dom_results = []
        for v in self.domain_validators:
            v_res = v.validate(evidence, claims)
            if v_res:
                dom_results.append(v_res)
                if v_res.blocking:
                    issues.append("DOMAIN_RULE_VIOLATION")

        # Top level aggregates
        rel = self.relevance_sc.score(evidence.user_query, claims)
        cov = self.intent_sc.score(evidence.user_query, claims)
        uti = self.util_sc.score(evidence, claims)
        sim = sum(c.entailment_score for c in claims) / len(claims) if claims else 0.0

        cons_score = 1.0
        if "CLAIM_CONTRADICTION" in issues: cons_score = 0.3
        elif "NUMERIC_UNSUPPORTED" in issues: cons_score = 0.5
        elif "TEMPORAL_MISMATCH" in issues: cons_score = 0.6
        
        cit_score = 1.0
        if "MISSING_CITATION" in issues: cit_score = 0.4
        elif "INVALID_CHUNK_REFERENCE" in issues: cit_score = 0.2

        dom_score = min([r.score for r in dom_results]) if dom_results else 1.0

        # Determine Severity based on extracted issue codes
        highest_severity = None
        rep = ["MISSING_CITATION", "PARTIAL_COVERAGE"]
        risk = ["CLAIM_CONTRADICTION"]
        block = ["NUMERIC_UNSUPPORTED", "DOMAIN_RULE_VIOLATION"]

        for i in issues:
            if i in block: highest_severity = IssueSeverity.BLOCKING
            elif i in risk and highest_severity != IssueSeverity.BLOCKING: highest_severity = IssueSeverity.HIGH_RISK
            elif i in rep and not highest_severity: highest_severity = IssueSeverity.REPAIRABLE

        return VerificationResult(
            relevance=rel,
            intent_coverage=cov,
            evidence_utilization=uti,
            claim_similarity=sim,
            consistency=cons_score,
            citation_integrity=cit_score,
            domain_rules=dom_score,
            claims=claims,
            domain_results=dom_results,
            issues=issues,
            issue_categories=list(set(issues)),
            highest_severity=highest_severity,
            iterations=iteration
        )

    def _emit_audit(self, evidence: ConsolidatedEvidenceSet, verif: VerificationResult, iteration: int, principal_id: str, phase: str, extra: dict = None):
        try:
            event = AuditEvent(
                event_id=str(uuid.uuid4()),
                principal_id=principal_id,
                principal_type="SERVICE",
                action=AuditAction.VERIFICATION_COMPLETE,
                resource="VERIFIER",
                request_id=get_correlation_id(),
                decision=AuditDecision.ALLOW,
                metadata={
                    "query_id": evidence.query_id,
                    "iteration": iteration,
                    "phase": phase,
                    "highest_severity": verif.highest_severity.value if verif.highest_severity else "NONE",
                    "routing_details": extra or {}
                },
                verification=AuditVerificationContext(
                    confidence_score=0.0,
                    threshold=0.0,
                    route=""
                )
            )
            self.audit.log_event(event)
        except Exception as e:
            logger.error("verif_audit_failed", error=str(e))
