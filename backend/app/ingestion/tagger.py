"""
Metadata Tagger Protocol
==========================

Extracts governed metadata fields from raw documents.
All tagging must comply with the approved metadata schema:
    - domain_tag: from controlled vocabulary
    - sensitivity_level: from classification engine
    - version: from source document
    - origin: from source system

No inferred or fabricated metadata values.
"""

from __future__ import annotations

import re
from typing import Any, Protocol, runtime_checkable

from app.core.exceptions import (
    ClassificationError,
    MetadataSchemaViolationError,
)
from app.core.logging import get_logger
from app.governance.classification import (
    ClassificationEngine,
    DefaultClassificationEngine,
)
from app.governance.vocabulary import ControlledVocabularyRegistry, vocabulary_registry
from app.ingestion.config import (
    DEFAULT_SOURCE_SYSTEM_MAPPINGS,
    SENSITIVITY_ESCALATION_PATTERNS,
    SourceSystemMapping,
)
from app.models.document import RawDocument
from app.models.metadata import DocumentMetadata, DomainTag, SensitivityLevel

logger = get_logger(__name__)


@runtime_checkable
class MetadataTagger(Protocol):
    """
    Protocol for extracting governed metadata from raw documents.

    Rules (from .antigravityrules):
    - domain_tag must resolve from central registry keyed by source_system
    - sensitivity_level must be computed via classification engine
    - version must follow source_version or ingestion sequence
    - origin must uniquely identify repository/location
    - No extra fields beyond the approved schema
    - No inferred values not present in source or governance tables
    """

    def tag(self, raw: RawDocument) -> DocumentMetadata:
        """
        Extract governed metadata from a raw document.

        Args:
            raw: Raw document from source system

        Returns:
            DocumentMetadata with exactly the 4 approved fields

        Raises:
            MetadataSchemaViolationError if metadata cannot be derived properly
            VocabularyViolationError if domain_tag is invalid
            ClassificationError if sensitivity cannot be determined
        """
        ...


class DefaultMetadataTagger:
    """
    Production metadata tagger.

    Derives governed metadata using:
    1. ControlledVocabularyRegistry for domain_tag resolution
    2. Source system mapping table for domain defaults
    3. ClassificationEngine for sensitivity_level derivation
    4. Content-based sensitivity escalation patterns
    5. Source document version extraction
    6. Canonical origin derivation from source_system + external_id

    Never fabricates values. Hard fails on unresolvable metadata.
    """

    def __init__(
        self,
        vocabulary: ControlledVocabularyRegistry | None = None,
        classification_engine: ClassificationEngine | None = None,
        source_mappings: list[SourceSystemMapping] | None = None,
    ) -> None:
        self._vocabulary = vocabulary or vocabulary_registry
        self._classification = classification_engine or DefaultClassificationEngine()
        self._source_mappings: dict[str, SourceSystemMapping] = {
            m.source_system: m
            for m in (source_mappings or DEFAULT_SOURCE_SYSTEM_MAPPINGS)
        }

    def tag(self, raw: RawDocument) -> DocumentMetadata:
        """
        Extract governed metadata from a raw document.

        Resolution order:
        1. domain_tag: source_system mapping → raw_metadata → GENERAL fallback
        2. sensitivity_level: content analysis → source mapping default → classification engine
        3. version: raw_metadata["version"] → updated_at timestamp
        4. origin: source_system/external_id canonical path
        """
        try:
            domain_tag = self._resolve_domain_tag(raw)
            sensitivity_level = self._resolve_sensitivity(raw)
            version = self._resolve_version(raw)
            origin = self._resolve_origin(raw)

            metadata = DocumentMetadata(
                domain_tag=domain_tag,
                sensitivity_level=sensitivity_level,
                version=version,
                origin=origin,
            )

            logger.info(
                "metadata_tagged",
                external_id=raw.external_id,
                source_system=raw.source_system,
                domain_tag=domain_tag.value,
                sensitivity=sensitivity_level.value,
                version=version,
            )

            return metadata

        except (MetadataSchemaViolationError, ClassificationError):
            raise
        except Exception as exc:
            logger.error(
                "metadata_tagging_failed",
                external_id=raw.external_id,
                source_system=raw.source_system,
                error=str(exc),
            )
            raise MetadataSchemaViolationError(
                message=f"Failed to derive metadata for document '{raw.external_id}': {exc}",
            ) from exc

    def _resolve_domain_tag(self, raw: RawDocument) -> DomainTag:
        """
        Resolve domain_tag:
        1. Source system mapping (primary)
        2. raw_metadata["domain_tag"] validated against vocabulary (fallback)
        3. GENERAL default (last resort)
        """
        mapping = self._source_mappings.get(raw.source_system)
        if mapping:
            return self._vocabulary.validate_domain_tag(mapping.domain_tag)

        return self._vocabulary.resolve_domain_tag(
            source_system=raw.source_system,
            raw_metadata=raw.raw_metadata,
        )

    def _resolve_sensitivity(self, raw: RawDocument) -> SensitivityLevel:
        """
        Resolve sensitivity_level:
        1. Content-based pattern escalation (highest match wins)
        2. raw_metadata["sensitivity_level"] if valid
        3. Source system mapping default
        4. ClassificationEngine derive

        The highest level across all sources is chosen (fail-conservative).
        """
        candidates: list[SensitivityLevel] = []

        # Content-based escalation
        content_level = self._scan_content_sensitivity(raw.body, raw.title)
        if content_level:
            candidates.append(content_level)

        # raw_metadata hint (validated)
        raw_sensitivity = raw.raw_metadata.get("sensitivity_level")
        if raw_sensitivity:
            try:
                candidates.append(SensitivityLevel(raw_sensitivity))
            except ValueError:
                logger.warning(
                    "invalid_raw_sensitivity",
                    external_id=raw.external_id,
                    value=raw_sensitivity,
                )

        # Source system mapping default
        mapping = self._source_mappings.get(raw.source_system)
        if mapping:
            try:
                candidates.append(SensitivityLevel(mapping.default_sensitivity))
            except ValueError:
                pass

        # Classification engine baseline
        engine_level = self._classification.classify(
            source_system=raw.source_system,
            raw_metadata=raw.raw_metadata,
            content_sample=raw.body[:2000] if raw.body else None,
        )
        candidates.append(engine_level)

        if not candidates:
            # Fail-closed: if no sensitivity can be determined, use most restrictive
            logger.warning(
                "sensitivity_fallback_to_secret",
                external_id=raw.external_id,
            )
            return SensitivityLevel.SECRET

        # Return the highest (most restrictive) level
        return max(candidates, key=lambda s: s.numeric_level)

    def _scan_content_sensitivity(
        self, body: str, title: str
    ) -> SensitivityLevel | None:
        """
        Scan document content against governance-approved sensitivity patterns.

        Returns the highest matching level, or None if no patterns match.
        """
        combined_text = f"{title}\n{body[:5000]}"  # Scan title + first 5K chars

        for level_str in ["SECRET", "CONFIDENTIAL", "INTERNAL"]:
            patterns = SENSITIVITY_ESCALATION_PATTERNS.get(level_str, [])
            for pattern in patterns:
                if re.search(pattern, combined_text):
                    logger.info(
                        "sensitivity_content_match",
                        level=level_str,
                        pattern=pattern[:50],
                    )
                    return SensitivityLevel(level_str)

        return None

    def _resolve_version(self, raw: RawDocument) -> str:
        """
        Resolve version:
        1. raw_metadata["version"] (explicit source version)
        2. raw_metadata["document_version"]
        3. Fallback to updated_at timestamp as batch ID
        """
        for key in ("version", "document_version", "doc_version"):
            val = raw.raw_metadata.get(key)
            if val and isinstance(val, str) and val.strip():
                return val.strip()

        # Fallback: use updated_at as version identifier
        return f"batch-{raw.updated_at.strftime('%Y%m%dT%H%M%S')}"

    def _resolve_origin(self, raw: RawDocument) -> str:
        """
        Derive canonical origin from source_system + external_id.

        Format: {source_system}/{external_id}
        This must uniquely identify the document across all ingestion cycles.
        """
        return f"{raw.source_system}/{raw.external_id}"
