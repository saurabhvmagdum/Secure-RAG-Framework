"""
Answer Router Protocol
========================

Threshold routing decision tree:
- confidence >= domain_threshold → HIGH_CONFIDENCE
- hard_block_below <= confidence < domain_threshold → FALLBACK_PARTIAL
- confidence < hard_block_below → BLOCKED

Per-domain thresholds from docs/verification_and_grounding_loop.md:
    - procurement: 0.9
    - telemetry: 0.85
    - failure_analysis: 0.9
    - default: 0.8
    - hard_block: 0.5
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.answer import RoutingDecision, RoutingRoute


@runtime_checkable
class AnswerRouter(Protocol):
    """
    Protocol for routing verified answers based on confidence thresholds.
    """

    def route(
        self,
        domain_tag: str,
        confidence: float,
        metrics: dict[str, float],
    ) -> RoutingDecision:
        """
        Determine the routing decision for an answer.

        Args:
            domain_tag: Domain classification of the query
            confidence: Computed confidence score
            metrics: Detailed verification metrics

        Returns:
            RoutingDecision with route, confidence, and explanation
        """
        ...


class DefaultAnswerRouter:
    """
    Default answer router using governance-configured thresholds.

    Implements the decision logic from docs/verification_and_grounding_loop.md.
    """

    def __init__(self) -> None:
        from app.config import settings

        self._settings = settings.governance

    def route(
        self,
        domain_tag: str,
        confidence: float,
        metrics: dict[str, float],
    ) -> RoutingDecision:
        """Apply threshold routing."""
        threshold = self._settings.get_domain_threshold(domain_tag)
        hard_block = self._settings.governance_hard_block_below

        if confidence < hard_block:
            return RoutingDecision(
                route=RoutingRoute.BLOCKED,
                confidence=confidence,
                threshold_applied=threshold,
                explanation=(
                    f"Confidence {confidence:.2f} below hard safety threshold "
                    f"{hard_block:.2f}; surface evidence-only view."
                ),
            )

        if confidence >= threshold:
            return RoutingDecision(
                route=RoutingRoute.HIGH_CONFIDENCE,
                confidence=confidence,
                threshold_applied=threshold,
                explanation=(
                    f"Confidence {confidence:.2f} ≥ threshold {threshold:.2f}."
                ),
            )

        if self._settings.governance_allow_partial:
            return RoutingDecision(
                route=RoutingRoute.FALLBACK_PARTIAL,
                confidence=confidence,
                threshold_applied=threshold,
                explanation=(
                    f"Confidence {confidence:.2f} below threshold {threshold:.2f}; "
                    "return curated evidence snippets and caveats instead of "
                    "a synthesized answer."
                ),
            )

        return RoutingDecision(
            route=RoutingRoute.BLOCKED,
            confidence=confidence,
            threshold_applied=threshold,
            explanation="Sub-threshold answer not permitted for this domain.",
        )
