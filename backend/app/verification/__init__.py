"""
Verification package — Verification loop, confidence scoring, and routing interfaces.
"""

from app.verification.config import DEFAULT_THRESHOLDS, DOMAIN_OVERRIDES, METRIC_FLOORS
from app.verification.metrics import (
    RelevanceScorer, IntentCoverageScorer, EvidenceUtilizationScorer,
    ClaimSimilarityScorer, ConsistencyScorer, CitationIntegrityScorer
)
from app.verification.rules import DomainValidator, ProcurementRuleValidator
from app.verification.scorer import WeightedConfidenceScorer, ThresholdRouter
from app.verification.fallback import FallbackFormatter
from app.verification.verifier import DefaultVerificationLoop

__all__ = [
    "DEFAULT_THRESHOLDS", "DOMAIN_OVERRIDES", "METRIC_FLOORS",
    "RelevanceScorer", "IntentCoverageScorer", "EvidenceUtilizationScorer",
    "ClaimSimilarityScorer", "ConsistencyScorer", "CitationIntegrityScorer",
    "DomainValidator", "ProcurementRuleValidator",
    "WeightedConfidenceScorer", "ThresholdRouter", "FallbackFormatter",
    "DefaultVerificationLoop"
]
