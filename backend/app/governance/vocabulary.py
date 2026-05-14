"""
Controlled Vocabulary Registry
===============================

Manages the approved set of domain_tag values. Any metadata tagging
operation must validate domain_tag against this registry.

Phase 2: Implements source_system → domain_tag mapping table with:
- Governed mapping from known source systems
- Hierarchical resolution (exact match → prefix match → GENERAL)
- Document type to domain mapping fallback
- Validation with hard-fail on unknown values
"""

from __future__ import annotations

from app.core.exceptions import VocabularyViolationError
from app.core.logging import get_logger
from app.models.metadata import DomainTag

logger = get_logger(__name__)


# ── Governed Source System → Domain Mapping ──────────────────────────────────
# New entries require governance approval. Must be added here AND in the
# SourceSystemMapping in ingestion/config.py.

SOURCE_SYSTEM_TO_DOMAIN: dict[str, DomainTag] = {
    # Technical document management
    "EDMS": DomainTag.GENERAL,
    "EDMS-Propulsion": DomainTag.PROPULSION,
    "EDMS-Avionics": DomainTag.AVIONICS,
    "EDMS-Structures": DomainTag.STRUCTURES,
    "EDMS-Thermal": DomainTag.THERMAL,
    "EDMS-Navigation": DomainTag.NAVIGATION,
    # Knowledge bases
    "QAKnowledgeBase": DomainTag.GENERAL,
    "QualityDB": DomainTag.QUALITY_ASSURANCE,
    # Failure & telemetry
    "FailureDB": DomainTag.FAILURE_ANALYSIS,
    "TelemetryDB": DomainTag.TELEMETRY,
    # Administrative
    "ProcurementPortal": DomainTag.PROCUREMENT,
    "AdminDMS": DomainTag.ADMINISTRATION,
    "HRMS": DomainTag.HUMAN_RESOURCES,
    # Operations
    "MissionPlanning": DomainTag.MISSION_PLANNING,
    "LaunchOps": DomainTag.LAUNCH_OPERATIONS,
    "GroundStation": DomainTag.GROUND_SYSTEMS,
}

# ── Document Type → Domain Fallback Mapping ─────────────────────────────────
# Used when source_system is not in the primary mapping.
DOCUMENT_TYPE_TO_DOMAIN: dict[str, DomainTag] = {
    "technical_manual": DomainTag.GENERAL,
    "failure_report": DomainTag.FAILURE_ANALYSIS,
    "failure_analysis": DomainTag.FAILURE_ANALYSIS,
    "telemetry_narrative": DomainTag.TELEMETRY,
    "telemetry_story": DomainTag.TELEMETRY,
    "procurement_rule": DomainTag.PROCUREMENT,
    "procurement_policy": DomainTag.PROCUREMENT,
    "admin_note": DomainTag.ADMINISTRATION,
    "admin_memo": DomainTag.ADMINISTRATION,
    "qa_document": DomainTag.GENERAL,
    "mission_plan": DomainTag.MISSION_PLANNING,
    "launch_procedure": DomainTag.LAUNCH_OPERATIONS,
    "ground_procedure": DomainTag.GROUND_SYSTEMS,
    "quality_report": DomainTag.QUALITY_ASSURANCE,
}


class ControlledVocabularyRegistry:
    """
    Registry for governed vocabulary values.

    Manages domain_tag resolution with a three-tier strategy:
    1. Exact source_system match in governed mapping
    2. Prefix match (e.g., "EDMS-" prefix for all EDMS sub-systems)
    3. Document type fallback mapping
    4. GENERAL default (last resort, logged as warning)
    """

    def __init__(self) -> None:
        """Initialize with all approved domain tags from the enum."""
        self._domain_tags: frozenset[str] = frozenset(tag.value for tag in DomainTag)
        self._source_mapping = dict(SOURCE_SYSTEM_TO_DOMAIN)
        self._doctype_mapping = dict(DOCUMENT_TYPE_TO_DOMAIN)

    @property
    def domain_tags(self) -> frozenset[str]:
        """Return all approved domain tag values."""
        return self._domain_tags

    def validate_domain_tag(self, value: str) -> DomainTag:
        """
        Validate a domain_tag value against the controlled vocabulary.

        Raises:
            VocabularyViolationError if the value is not in the approved list
        """
        if value not in self._domain_tags:
            logger.warning(
                "vocabulary_violation",
                field="domain_tag",
                value=value,
                allowed=sorted(self._domain_tags),
            )
            raise VocabularyViolationError(
                field_name="domain_tag",
                invalid_value=value,
                allowed_values=sorted(self._domain_tags),
            )

        return DomainTag(value)

    def is_valid_domain_tag(self, value: str) -> bool:
        """Check if a domain_tag value is valid without raising."""
        return value in self._domain_tags

    def resolve_domain_tag(
        self,
        source_system: str,
        document_type: str | None = None,
        raw_metadata: dict[str, str] | None = None,
    ) -> DomainTag:
        """
        Resolve domain_tag from source system and document type.

        Resolution order:
        1. Exact source_system match in governed mapping
        2. Prefix match on source_system (e.g., "EDMS-*")
        3. raw_metadata["domain_tag"] if present and valid
        4. document_type fallback mapping
        5. GENERAL default (logged as warning)

        Args:
            source_system: Origin system identifier
            document_type: Optional document type from source
            raw_metadata: Optional raw metadata for additional context

        Returns:
            Resolved DomainTag
        """
        # 1. Exact source_system match
        if source_system in self._source_mapping:
            tag = self._source_mapping[source_system]
            logger.debug(
                "vocabulary_resolve_exact",
                source_system=source_system,
                resolved=tag.value,
            )
            return tag

        # 2. Prefix match (e.g., "EDMS-CustomSubsystem" → check "EDMS-" prefixes)
        for known_source, tag in self._source_mapping.items():
            if source_system.startswith(known_source + "-"):
                logger.info(
                    "vocabulary_resolve_prefix",
                    source_system=source_system,
                    matched_prefix=known_source,
                    resolved=tag.value,
                )
                return tag

        # 3. raw_metadata domain_tag hint
        if raw_metadata and "domain_tag" in raw_metadata:
            raw_tag = raw_metadata["domain_tag"]
            if self.is_valid_domain_tag(raw_tag):
                logger.info(
                    "vocabulary_resolve_metadata",
                    source_system=source_system,
                    raw_tag=raw_tag,
                )
                return DomainTag(raw_tag)
            else:
                logger.warning(
                    "vocabulary_invalid_metadata_hint",
                    source_system=source_system,
                    raw_tag=raw_tag,
                )

        # 4. Document type fallback
        if document_type:
            doc_type_lower = document_type.lower().replace(" ", "_")
            if doc_type_lower in self._doctype_mapping:
                tag = self._doctype_mapping[doc_type_lower]
                logger.info(
                    "vocabulary_resolve_doctype",
                    source_system=source_system,
                    document_type=document_type,
                    resolved=tag.value,
                )
                return tag

        # 5. Default to GENERAL — log as warning
        logger.warning(
            "vocabulary_resolve_default",
            source_system=source_system,
            document_type=document_type,
            resolved="general",
            reason="no_mapping_found",
        )
        return DomainTag.GENERAL

    def register_source_mapping(
        self, source_system: str, domain_tag: DomainTag
    ) -> None:
        """
        Register a new source system → domain_tag mapping.

        In production, this should only be called during startup from
        governed configuration. Runtime registration is logged for audit.
        """
        self._source_mapping[source_system] = domain_tag
        logger.info(
            "vocabulary_mapping_registered",
            source_system=source_system,
            domain_tag=domain_tag.value,
        )

    def get_all_source_mappings(self) -> dict[str, str]:
        """Return all registered source system → domain_tag mappings."""
        return {k: v.value for k, v in self._source_mapping.items()}


# ── Module-level singleton ──────────────────────────────────────────────────
vocabulary_registry = ControlledVocabularyRegistry()
