"""
Confidence Scorer Protocol
============================

Computes a scalar confidence score C ∈ [0,1] from verification metrics
using a weighted aggregation formula:

    C = w_r·R + w_c·Cv + w_s·S + w_k·K + w_d·D

Where:
    R = relevance, Cv = coverage, S = similarity,
    K = consistency, D = domain_rules

Weights are governance-tuned and may differ per domain_tag and sensitivity_level.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.answer import VerificationResult


@runtime_checkable
class ConfidenceScorer(Protocol):
    """
    Protocol for confidence score computation.

    Weights and minimum per-metric thresholds are defined in governance
    configuration, potentially varying by domain_tag and sensitivity_level.
    """

    def compute(
        self,
        verification: VerificationResult,
        domain_tag: str | None = None,
    ) -> float:
        """
        Compute the scalar confidence score.

        Args:
            verification: Multi-metric verification result
            domain_tag: Optional domain for domain-specific weights

        Returns:
            Confidence score in [0.0, 1.0]
        """
        ...

    def get_weights(self, domain_tag: str | None = None) -> dict[str, float]:
        """Get the confidence weights for a given domain (or defaults)."""
        ...


class DefaultConfidenceScorer:
    """
    Default confidence scorer using governance-configured weights.

    Reads weights from GovernanceSettings.
    """

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        if weights:
            self._weights = weights
        else:
            from app.config import settings

            self._weights = {
                "relevance": settings.governance.weight_relevance,
                "coverage": settings.governance.weight_coverage,
                "similarity": settings.governance.weight_similarity,
                "consistency": settings.governance.weight_consistency,
                "domain_rules": settings.governance.weight_domain_rules,
            }

    def compute(
        self,
        verification: VerificationResult,
        domain_tag: str | None = None,
    ) -> float:
        """Compute weighted confidence score."""
        weights = self.get_weights(domain_tag)
        metrics = verification.all_metrics

        score = sum(
            weights.get(metric, 0.0) * value
            for metric, value in metrics.items()
        )

        # Clamp to [0, 1]
        return max(0.0, min(1.0, score))

    def get_weights(self, domain_tag: str | None = None) -> dict[str, float]:
        """
        Get weights — currently returns default weights.
        TODO: Phase 2 — per-domain weight overrides.
        """
        return dict(self._weights)
