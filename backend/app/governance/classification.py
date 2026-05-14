"""
Data Classification Engine
===========================

Defines DataClassificationRule and the ClassificationEngine protocol.
Classification rules determine encryption scope, retention policy,
index eligibility, and access constraints for each sensitivity level.

Phase 2: Implements content-based classification with:
- Source system mapping
- Regex pattern scanning for sensitivity escalation
- Ownership / label based derivation
- Fail-closed defaults (most restrictive on error)
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.models.metadata import SensitivityLevel

logger = get_logger(__name__)


class DataClassificationRule(BaseModel):
    """
    Classification rule defining security controls for a sensitivity level.

    Per docs/data_layer.md specification.
    """

    classification: SensitivityLevel = Field(
        ...,
        description="Sensitivity level this rule applies to",
    )
    encryption_at_rest: str = Field(
        default="AES-256-GCM",
        description="Encryption algorithm for data at rest",
    )
    encryption_in_transit: str = Field(
        default="TLS1.3",
        description="Encryption protocol for data in transit",
    )
    key_scope: str = Field(
        default="per-domain",
        description='Key scope: "per-tenant", "per-domain", or "global"',
    )
    retention_policy_days: int = Field(
        default=365,
        ge=1,
        description="Minimum data retention period in days",
    )
    allowed_indices: list[str] = Field(
        default_factory=lambda: ["keyword", "semantic", "graph"],
        description="Index types this classification level may be stored in",
    )
    require_audit_on_access: bool = Field(
        default=False,
        description="Whether every read access must be audit-logged",
    )

    model_config = {"extra": "forbid"}


# ── Default Classification Rules ────────────────────────────────────────────
DEFAULT_CLASSIFICATION_RULES: dict[SensitivityLevel, DataClassificationRule] = {
    SensitivityLevel.PUBLIC: DataClassificationRule(
        classification=SensitivityLevel.PUBLIC,
        encryption_at_rest="AES-256-GCM",
        encryption_in_transit="TLS1.3",
        key_scope="global",
        retention_policy_days=365,
        allowed_indices=["keyword", "semantic", "graph"],
        require_audit_on_access=False,
    ),
    SensitivityLevel.INTERNAL: DataClassificationRule(
        classification=SensitivityLevel.INTERNAL,
        encryption_at_rest="AES-256-GCM",
        encryption_in_transit="TLS1.3",
        key_scope="per-domain",
        retention_policy_days=730,
        allowed_indices=["keyword", "semantic", "graph"],
        require_audit_on_access=False,
    ),
    SensitivityLevel.CONFIDENTIAL: DataClassificationRule(
        classification=SensitivityLevel.CONFIDENTIAL,
        encryption_at_rest="AES-256-GCM",
        encryption_in_transit="TLS1.3",
        key_scope="per-domain",
        retention_policy_days=1825,
        allowed_indices=["keyword", "semantic", "graph"],
        require_audit_on_access=True,
    ),
    SensitivityLevel.SECRET: DataClassificationRule(
        classification=SensitivityLevel.SECRET,
        encryption_at_rest="AES-256-GCM",
        encryption_in_transit="TLS1.3",
        key_scope="per-tenant",
        retention_policy_days=3650,
        allowed_indices=["semantic", "graph"],  # No keyword index for SECRET
        require_audit_on_access=True,
    ),
}

# ── Source System Sensitivity Baselines ──────────────────────────────────────
# Governance-approved default sensitivity for each source system.
# Content-based analysis can ONLY escalate, never downgrade.

SOURCE_SYSTEM_BASELINES: dict[str, SensitivityLevel] = {
    "EDMS": SensitivityLevel.INTERNAL,
    "EDMS-Propulsion": SensitivityLevel.CONFIDENTIAL,
    "EDMS-Avionics": SensitivityLevel.CONFIDENTIAL,
    "QAKnowledgeBase": SensitivityLevel.INTERNAL,
    "FailureDB": SensitivityLevel.CONFIDENTIAL,
    "TelemetryDB": SensitivityLevel.CONFIDENTIAL,
    "ProcurementPortal": SensitivityLevel.INTERNAL,
    "AdminDMS": SensitivityLevel.INTERNAL,
    "MissionPlanning": SensitivityLevel.SECRET,
    "QualityDB": SensitivityLevel.INTERNAL,
    "LaunchOps": SensitivityLevel.CONFIDENTIAL,
    "GroundStation": SensitivityLevel.CONFIDENTIAL,
}


@runtime_checkable
class ClassificationEngine(Protocol):
    """
    Protocol for data classification operations.

    Implementations must:
    - Derive sensitivity_level from source content, ownership, and labels
    - Never allow free-text sensitivity assignment
    - Return the applicable DataClassificationRule
    - Validate that data is stored only in permitted indices
    """

    def classify(
        self,
        source_system: str,
        raw_metadata: dict[str, str],
        content_sample: str | None = None,
    ) -> SensitivityLevel:
        """Determine the sensitivity level for a document."""
        ...

    def get_rule(self, level: SensitivityLevel) -> DataClassificationRule:
        """Get the classification rule for a given sensitivity level."""
        ...

    def validate_index_eligibility(
        self,
        level: SensitivityLevel,
        index_type: str,
    ) -> bool:
        """Check whether data may be stored in the given index."""
        ...


class DefaultClassificationEngine:
    """
    Production classification engine.

    Resolution strategy:
    1. Start with source system baseline (governance-approved default)
    2. Check raw_metadata for explicit sensitivity labels
    3. Scan content sample against escalation patterns
    4. Return the HIGHEST (most restrictive) level found

    Content analysis can ONLY escalate, never downgrade.
    Unknown sources default to INTERNAL (fail-conservative).
    """

    def __init__(
        self,
        rules: dict[SensitivityLevel, DataClassificationRule] | None = None,
        source_baselines: dict[str, SensitivityLevel] | None = None,
    ) -> None:
        self._rules = rules or DEFAULT_CLASSIFICATION_RULES
        self._baselines = source_baselines or SOURCE_SYSTEM_BASELINES

    def classify(
        self,
        source_system: str,
        raw_metadata: dict[str, str],
        content_sample: str | None = None,
    ) -> SensitivityLevel:
        """
        Classify document sensitivity.

        Strategy:
        1. Source system baseline
        2. raw_metadata["sensitivity_level"] if valid
        3. Content pattern scanning (escalation only)
        4. Return max(all candidates)
        """
        candidates: list[SensitivityLevel] = []

        # 1. Source system baseline
        baseline = self._baselines.get(source_system, SensitivityLevel.INTERNAL)
        candidates.append(baseline)

        logger.info(
            "classification_baseline",
            source_system=source_system,
            baseline=baseline.value,
        )

        # 2. raw_metadata hint
        meta_sensitivity = raw_metadata.get("sensitivity_level", "")
        if meta_sensitivity:
            try:
                candidates.append(SensitivityLevel(meta_sensitivity))
            except ValueError:
                logger.warning(
                    "classification_invalid_metadata_hint",
                    value=meta_sensitivity,
                    source_system=source_system,
                )

        # 3. Content-based escalation
        if content_sample:
            content_level = self._scan_content(content_sample)
            if content_level:
                candidates.append(content_level)

        # Return highest (most restrictive)
        result = max(candidates, key=lambda s: s.numeric_level)

        logger.info(
            "classification_result",
            source_system=source_system,
            result=result.value,
            candidates=[c.value for c in candidates],
        )

        return result

    def get_rule(self, level: SensitivityLevel) -> DataClassificationRule:
        """Get classification rule. Defaults to most restrictive if not found."""
        return self._rules.get(
            level,
            self._rules[SensitivityLevel.SECRET],  # Fail-closed
        )

    def validate_index_eligibility(
        self,
        level: SensitivityLevel,
        index_type: str,
    ) -> bool:
        """Check index eligibility for a classification level."""
        rule = self.get_rule(level)
        eligible = index_type.lower() in rule.allowed_indices

        if not eligible:
            logger.warning(
                "classification_index_ineligible",
                level=level.value,
                index_type=index_type,
                allowed=rule.allowed_indices,
            )

        return eligible

    def get_encryption_policy(self, level: SensitivityLevel) -> dict[str, str]:
        """Get encryption policy for a sensitivity level."""
        rule = self.get_rule(level)
        return {
            "at_rest": rule.encryption_at_rest,
            "in_transit": rule.encryption_in_transit,
            "key_scope": rule.key_scope,
        }

    def get_retention_days(self, level: SensitivityLevel) -> int:
        """Get minimum retention period for a sensitivity level."""
        return self.get_rule(level).retention_policy_days

    @staticmethod
    def _scan_content(text: str) -> SensitivityLevel | None:
        """
        Scan text for sensitivity escalation patterns.

        Uses governance-approved patterns only — no ML inference.
        Returns the highest matching level or None.
        """
        from app.ingestion.config import SENSITIVITY_ESCALATION_PATTERNS

        for level_str in ["SECRET", "CONFIDENTIAL", "INTERNAL"]:
            patterns = SENSITIVITY_ESCALATION_PATTERNS.get(level_str, [])
            for pattern in patterns:
                if re.search(pattern, text[:5000]):
                    return SensitivityLevel(level_str)

        return None
