"""
Mathematical Scoring & Routing Boundaries
=========================================

Handles additive verification scores, clamps based on contradictions
and numeric violations, and evaluates thresholds according to policies.
"""

from __future__ import annotations

from app.models.answer import VerificationResult, RoutingDecision, RoutingRoute
from app.verification.config import DEFAULT_THRESHOLDS, DOMAIN_OVERRIDES, METRIC_FLOORS


class WeightedConfidenceScorer:
    
    def compute(self, result: VerificationResult) -> float:
        
        # Additive model as specified
        base_score = (
            0.25 * result.relevance +
            0.20 * result.intent_coverage +
            0.25 * result.claim_similarity +
            0.20 * result.consistency +
            0.10 * result.domain_rules
        )

        uncited_claims = 0
        total_claims = len(result.claims) if result.claims else 1

        contradiction_detected = False
        unsupported_numeric = False
        blocking_domain = False

        for claim in result.claims:
            if "CLAIM_CONTRADICTION" in claim.issues:
                contradiction_detected = True
            if "NUMERIC_UNSUPPORTED" in claim.issues:
                unsupported_numeric = True
            if not claim.cited_chunk_ids:
                uncited_claims += 1

        for dom in result.domain_results:
            if dom.blocking:
                blocking_domain = True

        uncited_ratio = uncited_claims / total_claims

        # Explicit Penalty Bounds
        if contradiction_detected:
            base_score = min(base_score, 0.40)

        if uncited_ratio > 0:
            base_score *= max(0.0, 1.0 - uncited_ratio)

        if unsupported_numeric:
            base_score = min(base_score, 0.35)

        if blocking_domain:
            return 0.0 # Strict flat bottom
            
        return max(0.0, min(base_score, 1.0))


class ThresholdRouter:
    
    def route(self, result: VerificationResult, confidence: float, max_sensitivity: str, domain_tags: list[str]) -> RoutingDecision:
        
        # Determine strict threshold
        threshold = DEFAULT_THRESHOLDS.get(max_sensitivity.upper(), 1.0)
        
        for t in domain_tags:
            if t in DOMAIN_OVERRIDES:
                threshold = max(threshold, DOMAIN_OVERRIDES[t])

        explanation = f"Base threshold computed {threshold}"
        reason_codes = []
        route = RoutingRoute.HIGH_CONFIDENCE

        # Check Floors
        for name, floor in METRIC_FLOORS.items():
            if getattr(result, name) < floor:
                explanation = f"Metric floor failure on {name}: {getattr(result, name)} < {floor}"
                route = RoutingRoute.FALLBACK_PARTIAL
                reason_codes.append(f"FLOOR_{name.upper()}")

        if "CLAIM_CONTRADICTION" in result.issues:
            route = RoutingRoute.FALLBACK_PARTIAL
            explanation = "Contradictions degrade answer trust."
            reason_codes.append("CLAIM_CONTRADICTION")

        if confidence == 0.0:
            route = RoutingRoute.BLOCKED
            explanation = "Confidence zeroed due to blocking rule or unverified numbers."
            reason_codes.append("BLOCKED_CONFIDENCE")

        if confidence < threshold and route == RoutingRoute.HIGH_CONFIDENCE:
            route = RoutingRoute.FALLBACK_PARTIAL
            explanation = f"Total Confidence {confidence:.2f} failed to pass threshold {threshold:.2f}."
            reason_codes.append("INSUFFICIENT_CONF")

        if route == RoutingRoute.FALLBACK_PARTIAL and max_sensitivity == "SECRET":
            # Secret fails safe to blocked if it's not perfect
            route = RoutingRoute.BLOCKED
            reason_codes.append("SECRET_FALLBACK_DENIED")
            explanation = "Secret sensitivity bypasses fallback into complete block."

        return RoutingDecision(
            route=route,
            confidence=confidence,
            threshold_applied=threshold,
            explanation=explanation,
            reason_codes=reason_codes
        )
