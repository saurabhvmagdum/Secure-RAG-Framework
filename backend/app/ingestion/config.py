"""
Ingestion Configuration
========================

Ingestion-specific settings: chunk sizes, source system mappings,
document type registrations, and parser configuration.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class DataSourceType(str, Enum):
    """Supported data source types per project specification."""

    QA_DOCS = "qa_docs"
    FAILURE_ANALYSIS = "failure_analysis"
    TECHNICAL_MANUAL = "technical_manual"
    TELEMETRY_STORIES = "telemetry_stories"
    PROCUREMENT_RULES = "procurement_rules"
    ADMIN_NOTES = "admin_notes"


class SourceSystemMapping(BaseModel):
    """Maps a source_system identifier to its domain_tag and default sensitivity."""

    source_system: str = Field(..., description="Source system identifier")
    domain_tag: str = Field(..., description="Default domain_tag for this source")
    default_sensitivity: str = Field(
        default="INTERNAL",
        description="Default sensitivity if not determined by content analysis",
    )
    data_source_type: DataSourceType = Field(
        ..., description="Type of data source for parser selection",
    )

    model_config = {"extra": "forbid"}


# ── Default Source System Mappings ───────────────────────────────────────────
# These map each known source_system to its governed domain_tag.
# New source systems require governance approval before ingestion.

DEFAULT_SOURCE_SYSTEM_MAPPINGS: list[SourceSystemMapping] = [
    SourceSystemMapping(
        source_system="EDMS",
        domain_tag="general",
        default_sensitivity="INTERNAL",
        data_source_type=DataSourceType.TECHNICAL_MANUAL,
    ),
    SourceSystemMapping(
        source_system="EDMS-Propulsion",
        domain_tag="propulsion",
        default_sensitivity="CONFIDENTIAL",
        data_source_type=DataSourceType.TECHNICAL_MANUAL,
    ),
    SourceSystemMapping(
        source_system="EDMS-Avionics",
        domain_tag="avionics",
        default_sensitivity="CONFIDENTIAL",
        data_source_type=DataSourceType.TECHNICAL_MANUAL,
    ),
    SourceSystemMapping(
        source_system="QAKnowledgeBase",
        domain_tag="general",
        default_sensitivity="INTERNAL",
        data_source_type=DataSourceType.QA_DOCS,
    ),
    SourceSystemMapping(
        source_system="FailureDB",
        domain_tag="failure_analysis",
        default_sensitivity="CONFIDENTIAL",
        data_source_type=DataSourceType.FAILURE_ANALYSIS,
    ),
    SourceSystemMapping(
        source_system="TelemetryDB",
        domain_tag="telemetry",
        default_sensitivity="CONFIDENTIAL",
        data_source_type=DataSourceType.TELEMETRY_STORIES,
    ),
    SourceSystemMapping(
        source_system="ProcurementPortal",
        domain_tag="procurement",
        default_sensitivity="INTERNAL",
        data_source_type=DataSourceType.PROCUREMENT_RULES,
    ),
    SourceSystemMapping(
        source_system="AdminDMS",
        domain_tag="administration",
        default_sensitivity="INTERNAL",
        data_source_type=DataSourceType.ADMIN_NOTES,
    ),
    SourceSystemMapping(
        source_system="MissionPlanning",
        domain_tag="mission_planning",
        default_sensitivity="SECRET",
        data_source_type=DataSourceType.TECHNICAL_MANUAL,
    ),
    SourceSystemMapping(
        source_system="QualityDB",
        domain_tag="quality_assurance",
        default_sensitivity="INTERNAL",
        data_source_type=DataSourceType.QA_DOCS,
    ),
    SourceSystemMapping(
        source_system="LaunchOps",
        domain_tag="launch_operations",
        default_sensitivity="CONFIDENTIAL",
        data_source_type=DataSourceType.TECHNICAL_MANUAL,
    ),
    SourceSystemMapping(
        source_system="GroundStation",
        domain_tag="ground_systems",
        default_sensitivity="CONFIDENTIAL",
        data_source_type=DataSourceType.TELEMETRY_STORIES,
    ),
]


class ChunkingSettings(BaseModel):
    """Chunking configuration."""

    max_chunk_chars: int = Field(
        default=1500,
        ge=100,
        le=10000,
        description="Maximum characters per chunk",
    )
    chunk_overlap_chars: int = Field(
        default=200,
        ge=0,
        le=1000,
        description="Character overlap between consecutive chunks",
    )
    min_chunk_chars: int = Field(
        default=100,
        ge=10,
        description="Minimum characters for a valid chunk (smaller chunks are merged)",
    )
    respect_sentence_boundaries: bool = Field(
        default=True,
        description="Prefer splitting at sentence boundaries",
    )
    respect_paragraph_boundaries: bool = Field(
        default=True,
        description="Prefer splitting at paragraph boundaries",
    )
    section_heading_patterns: list[str] = Field(
        default_factory=lambda: [
            r"^#{1,6}\s+",           # Markdown headings
            r"^Chapter\s+\d+",       # Chapter markers
            r"^Section\s+\d+",       # Section markers
            r"^\d+\.\d+[\.\d]*\s+",  # Numbered sections (1.2, 1.2.3)
            r"^APPENDIX\s+",         # Appendix markers
            r"^ANNEX\s+",            # Annex markers
        ],
        description="Regex patterns identifying section headings",
    )

    model_config = {"extra": "forbid"}


class IngestionSettings(BaseSettings):
    """Ingestion pipeline settings."""

    ingestion_batch_size: int = Field(
        default=50,
        ge=1,
        description="Number of documents to process in a single batch",
    )
    ingestion_max_document_chars: int = Field(
        default=5_000_000,
        ge=1000,
        description="Maximum document size in characters (reject if larger)",
    )
    ingestion_require_title: bool = Field(
        default=True,
        description="Reject documents without a title",
    )
    ingestion_require_body: bool = Field(
        default=True,
        description="Reject documents with empty body",
    )
    ingestion_deduplicate_by_external_id: bool = Field(
        default=True,
        description="Skip re-ingestion of documents with same external_id + source_system",
    )

    model_config = {"env_prefix": "", "env_file": ".env", "case_sensitive": False}


# ── Sensitivity Keywords ────────────────────────────────────────────────────
# Used by the classification engine for content-based sensitivity detection.
# These are governance-approved patterns, not ML-inferred.

SENSITIVITY_ESCALATION_PATTERNS: dict[str, list[str]] = {
    "SECRET": [
        r"(?i)\bTOP\s+SECRET\b",
        r"(?i)\bSECRET\b",
        r"(?i)\bCLASSIFIED\b",
        r"(?i)\bRESTRICTED\s+DISTRIBUTION\b",
        r"(?i)\bORBITAL\s+PARAMETERS?\b",
        r"(?i)\bLAUNCH\s+CODES?\b",
        r"(?i)\bCRYPTOGRAPHIC\s+KEY\b",
    ],
    "CONFIDENTIAL": [
        r"(?i)\bCONFIDENTIAL\b",
        r"(?i)\bPROPRIETARY\b",
        r"(?i)\bFAILURE\s+MODE\b",
        r"(?i)\bROOT\s+CAUSE\s+ANALYSIS\b",
        r"(?i)\bANOMALY\s+REPORT\b",
        r"(?i)\bTELEMETRY\s+DUMP\b",
        r"(?i)\bDESIGN\s+SPECIFICATION\b",
    ],
    "INTERNAL": [
        r"(?i)\bINTERNAL\s+USE\s+ONLY\b",
        r"(?i)\bNOT\s+FOR\s+DISTRIBUTION\b",
        r"(?i)\bDRAFT\b",
        r"(?i)\bINTERNAL\s+MEMO\b",
    ],
}
