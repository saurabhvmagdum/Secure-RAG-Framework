"""
Document Normalizer
====================

Transforms RawDocument into NormalizedDocument.
Normalizers are deterministic and stateless. They:
- Generate stable doc_id via UUID5 from external_id + source_system
- Clean and normalize text (encoding, whitespace, structural markers)
- Derive governed metadata via MetadataTagger
- Validate all fields against governance schema

Governance checkpoint: ingestion.pre_normalization
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from typing import Protocol, runtime_checkable

from app.core.exceptions import IngestionError, MetadataSchemaViolationError
from app.core.logging import get_logger
from app.governance.checkpoint import governance_checkpoint
from app.ingestion.config import IngestionSettings
from app.ingestion.tagger import DefaultMetadataTagger, MetadataTagger
from app.models.document import NormalizedDocument, RawDocument

logger = get_logger(__name__)

# UUID5 namespace for generating deterministic doc IDs
_ISRO_RAG_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


@runtime_checkable
class Normalizer(Protocol):
    """
    Protocol for document normalization.

    Contract:
    - Deterministic: same input always produces same output
    - Stateless: no side effects between calls
    - Must generate a stable doc_id (UUID5 from external_id + source_system)
    - Must NOT fabricate or infer metadata values
    - sensitivity_level must be derived via ClassificationEngine, not free-text
    - Must clean/normalize text (encoding, whitespace, structural markers)
    """

    def normalize(self, raw: RawDocument) -> NormalizedDocument:
        """
        Transform a raw document into a normalized document.

        Args:
            raw: Raw document from source system

        Returns:
            NormalizedDocument with stable doc_id and governed metadata

        Raises:
            IngestionError on normalization failure
            MetadataSchemaViolationError on metadata validation failure
        """
        ...

    def validate(self, raw: RawDocument) -> list[str]:
        """
        Validate a raw document without normalizing.

        Returns:
            List of validation issues (empty if valid)
        """
        ...


class DefaultNormalizer:
    """
    Production document normalizer.

    Responsibilities:
    1. Validate raw document completeness
    2. Generate deterministic doc_id via UUID5(namespace, external_id + source_system)
    3. Normalize text (Unicode NFC, whitespace collapse, control char removal)
    4. Derive governed metadata via MetadataTagger
    5. Construct NormalizedDocument with full provenance
    """

    def __init__(
        self,
        tagger: MetadataTagger | None = None,
        settings: IngestionSettings | None = None,
    ) -> None:
        self._tagger: MetadataTagger = tagger or DefaultMetadataTagger()
        self._settings = settings or IngestionSettings()

    @governance_checkpoint(
        "ingestion.pre_normalization", require_principal=False
    )
    def normalize(self, raw: RawDocument) -> NormalizedDocument:
        """
        Normalize a raw document with governance checkpoint enforcement.

        Hard fails on any validation or metadata error.
        """
        # Step 1: Validate
        issues = self.validate(raw)
        if issues:
            raise IngestionError(
                message=f"Raw document validation failed: {'; '.join(issues)}",
                context={
                    "external_id": raw.external_id,
                    "source_system": raw.source_system,
                    "issues": issues,
                },
            )

        # Step 2: Generate deterministic doc_id
        doc_id = self._generate_doc_id(raw.external_id, raw.source_system)

        # Step 3: Normalize text
        normalized_title = self._normalize_text(raw.title)
        normalized_body = self._normalize_text(raw.body)

        # Step 4: Derive governed metadata (hard fail on error)
        metadata = self._tagger.tag(raw)

        # Step 5: Construct NormalizedDocument
        normalized = NormalizedDocument(
            doc_id=doc_id,
            title=normalized_title,
            body=normalized_body,
            created_at=raw.created_at,
            updated_at=raw.updated_at,
            source_system=raw.source_system,
            metadata=metadata,
        )

        logger.info(
            "document_normalized",
            doc_id=doc_id,
            external_id=raw.external_id,
            source_system=raw.source_system,
            body_chars=len(normalized_body),
            domain_tag=metadata.domain_tag.value,
            sensitivity=metadata.sensitivity_level.value,
        )

        return normalized

    def validate(self, raw: RawDocument) -> list[str]:
        """
        Validate a raw document without normalizing.

        Checks:
        - Title is not empty (if required)
        - Body is not empty (if required)
        - Body does not exceed max size
        - external_id is not empty
        - source_system is not empty
        """
        issues: list[str] = []

        if self._settings.ingestion_require_title and not raw.title.strip():
            issues.append("Title is empty or whitespace-only")

        if self._settings.ingestion_require_body and not raw.body.strip():
            issues.append("Body is empty or whitespace-only")

        if len(raw.body) > self._settings.ingestion_max_document_chars:
            issues.append(
                f"Body exceeds max size: {len(raw.body)} > "
                f"{self._settings.ingestion_max_document_chars}"
            )

        if not raw.external_id.strip():
            issues.append("external_id is empty")

        if not raw.source_system.strip():
            issues.append("source_system is empty")

        if raw.created_at > raw.updated_at:
            issues.append("created_at is after updated_at")

        return issues

    @staticmethod
    def _generate_doc_id(external_id: str, source_system: str) -> str:
        """
        Generate a deterministic UUID5 doc_id from external_id + source_system.

        Same input always produces the same doc_id, ensuring idempotent
        re-ingestion without duplicate entries.
        """
        seed = f"{source_system}:{external_id}"
        return str(uuid.uuid5(_ISRO_RAG_NAMESPACE, seed))

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        Normalize text content:
        1. Unicode NFC normalization
        2. Remove control characters (except newlines, tabs)
        3. Collapse multiple whitespace (preserve paragraph breaks)
        4. Strip leading/trailing whitespace
        """
        if not text:
            return ""

        # Unicode NFC normalization
        text = unicodedata.normalize("NFC", text)

        # Remove control characters except \n \r \t
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)

        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Collapse multiple blank lines to max 2 newlines (preserve paragraphs)
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Collapse multiple spaces/tabs within lines to single space
        text = re.sub(r"[^\S\n]+", " ", text)

        # Strip lines
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines)

        return text.strip()
