"""
Metadata Schemas
================

Strictly controlled metadata model. Only four fields are permitted per
.antigravityrules and governance policy:
    - domain_tag: from controlled vocabulary
    - sensitivity_level: from classification policy
    - version: from source document or ingestion batch
    - origin: canonical source repository / system identifier

No additional metadata fields may be added without governance approval.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator
from typing import Any

from app.core.constants import APPROVED_METADATA_FIELDS


class DomainTag(str, Enum):
    """
    Controlled vocabulary for document domain classification.

    Values must be managed through the ControlledVocabularyRegistry.
    New entries require governance approval.
    """

    PROPULSION = "propulsion"
    AVIONICS = "avionics"
    STRUCTURES = "structures"
    THERMAL = "thermal"
    NAVIGATION = "navigation"
    TELEMETRY = "telemetry"
    PROCUREMENT = "procurement"
    ADMINISTRATION = "administration"
    FAILURE_ANALYSIS = "failure_analysis"
    QUALITY_ASSURANCE = "quality_assurance"
    MISSION_PLANNING = "mission_planning"
    GROUND_SYSTEMS = "ground_systems"
    LAUNCH_OPERATIONS = "launch_operations"
    HUMAN_RESOURCES = "human_resources"
    GENERAL = "general"


class SensitivityLevel(str, Enum):
    """
    Data classification levels per governance policy.

    Ordered from least to most restrictive.
    Controls encryption scope, index partitioning, and access constraints.
    """

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    SECRET = "SECRET"

    @property
    def numeric_level(self) -> int:
        """Numeric ordering for comparison — higher is more sensitive."""
        _levels = {
            "PUBLIC": 0,
            "INTERNAL": 1,
            "CONFIDENTIAL": 2,
            "SECRET": 3,
        }
        return _levels[self.value]

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, SensitivityLevel):
            return NotImplemented
        return self.numeric_level >= other.numeric_level

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, SensitivityLevel):
            return NotImplemented
        return self.numeric_level > other.numeric_level

    def __le__(self, other: object) -> bool:
        if not isinstance(other, SensitivityLevel):
            return NotImplemented
        return self.numeric_level <= other.numeric_level

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SensitivityLevel):
            return NotImplemented
        return self.numeric_level < other.numeric_level


class DocumentMetadata(BaseModel):
    """
    Governed metadata attached to every document, chunk, and index entry.

    ONLY these four fields are permitted. No extra fields allowed.
    """

    domain_tag: DomainTag = Field(
        ...,
        description="Domain classification from controlled vocabulary",
    )
    sensitivity_level: SensitivityLevel = Field(
        ...,
        description="Data sensitivity level from classification policy",
    )
    version: str = Field(
        ...,
        min_length=1,
        description="Source document version or ingestion batch ID",
    )
    origin: str = Field(
        ...,
        min_length=1,
        description="Canonical source repository / system identifier",
    )

    model_config = {"extra": "forbid"}  # Reject any unexpected fields

    @model_validator(mode="before")
    @classmethod
    def _validate_no_extra_fields(cls, data: Any) -> Any:
        """
        Fail-closed: reject metadata containing unauthorized fields.

        This is defense-in-depth on top of Pydantic's extra='forbid'.
        """
        if isinstance(data, dict):
            extra_keys = set(data.keys()) - APPROVED_METADATA_FIELDS
            if extra_keys:
                raise ValueError(
                    f"Unauthorized metadata fields detected: {extra_keys}. "
                    f"Only {APPROVED_METADATA_FIELDS} are permitted."
                )
        return data
