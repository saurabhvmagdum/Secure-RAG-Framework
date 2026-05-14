"""
Source-Specific Document Parsers
==================================

Parses raw content from different data source types into RawDocument format.
Each parser handles the structural conventions of its source:
- Q&A Docs: question-answer pair extraction
- Failure Analysis Reports: structured failure/cause/action sections
- Technical Manuals: hierarchical section structure
- Telemetry Stories: time-series narrative with metrics
- Procurement Rules: clause/sub-clause legal structure
- Admin Notes: memo-style free text

Parsers are stateless and deterministic. They do NOT assign metadata —
that is the MetadataTagger's responsibility. Parsers only structure the
raw text and extract structural markers for section_path traceability.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.core.exceptions import IngestionError
from app.core.logging import get_logger
from app.ingestion.config import DataSourceType
from app.models.document import RawDocument

logger = get_logger(__name__)


class ParsedSection(BaseModel):
    """A structural section extracted from a raw document."""

    heading: str = Field(default="", description="Section heading text")
    body: str = Field(default="", description="Section body text")
    depth: int = Field(default=0, ge=0, description="Nesting depth")

    model_config = {"extra": "forbid"}


class ParseResult(BaseModel):
    """Result from a source-specific parser."""

    title: str = Field(..., description="Extracted document title")
    sections: list[ParsedSection] = Field(
        default_factory=list, description="Extracted structural sections"
    )
    assembled_body: str = Field(
        default="", description="Full reassembled body with section markers"
    )
    structural_metadata: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Non-governed structural hints (e.g., num_sections, has_appendix). "
            "These are NOT propagated to DocumentMetadata — they are for "
            "chunker section detection only."
        ),
    )

    model_config = {"extra": "forbid"}


@runtime_checkable
class DocumentParser(Protocol):
    """Protocol for source-specific document parsing."""

    def parse(self, raw_text: str, title: str = "") -> ParseResult:
        """
        Parse raw text into structured sections.

        Args:
            raw_text: Original document text
            title: Document title (may be empty)

        Returns:
            ParseResult with extracted sections and assembled body
        """
        ...

    @property
    def source_type(self) -> DataSourceType:
        """Which data source type this parser handles."""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# TECHNICAL MANUAL PARSER
# ─────────────────────────────────────────────────────────────────────────────


class TechnicalManualParser:
    """
    Parser for hierarchical technical manuals.

    Handles:
    - Numbered sections (1.2, 1.2.3)
    - Chapter/Section/Appendix markers
    - Procedure steps
    - Tables of contents (stripped)
    - Figure/Table references (preserved inline)
    """

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.TECHNICAL_MANUAL

    def parse(self, raw_text: str, title: str = "") -> ParseResult:
        sections = self._extract_sections(raw_text)

        # Strip table of contents if detected
        sections = [s for s in sections if not self._is_toc_section(s)]

        assembled = self._assemble_body(sections)

        return ParseResult(
            title=title or self._extract_title(raw_text),
            sections=sections,
            assembled_body=assembled,
            structural_metadata={
                "num_sections": str(len(sections)),
                "parser": "technical_manual",
            },
        )

    def _extract_sections(self, text: str) -> list[ParsedSection]:
        """Extract sections from technical manual text."""
        heading_pattern = re.compile(
            r"^(\d+(?:\.\d+)*)\s+(.+?)$|"
            r"^(Chapter|Section|APPENDIX|ANNEX)\s+(.+?)$|"
            r"^(#{1,6})\s+(.+?)$",
            re.MULTILINE,
        )

        sections: list[ParsedSection] = []
        last_end = 0

        matches = list(heading_pattern.finditer(text))

        for i, match in enumerate(matches):
            # Capture text before this heading as part of previous section
            if i == 0 and match.start() > 0:
                preamble = text[last_end : match.start()].strip()
                if preamble:
                    sections.append(ParsedSection(heading="Preamble", body=preamble, depth=0))

            # Determine heading text and depth
            if match.group(1):  # Numbered section
                heading = f"{match.group(1)} {match.group(2)}"
                depth = match.group(1).count(".")
            elif match.group(3):  # Chapter/Section/Appendix
                heading = f"{match.group(3)} {match.group(4)}"
                depth = 0
            else:  # Markdown
                heading = match.group(6)
                depth = len(match.group(5)) - 1

            # Get section body (text until next heading)
            next_start = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[match.end() : next_start].strip()

            sections.append(ParsedSection(heading=heading, body=body, depth=depth))
            last_end = next_start

        if not sections:
            sections = [ParsedSection(heading="", body=text.strip(), depth=0)]

        return sections

    @staticmethod
    def _is_toc_section(section: ParsedSection) -> bool:
        """Detect table of contents sections."""
        toc_markers = ["table of contents", "contents", "index"]
        return section.heading.lower().strip() in toc_markers

    @staticmethod
    def _assemble_body(sections: list[ParsedSection]) -> str:
        """Reassemble sections into a single body with heading markers."""
        parts: list[str] = []
        for section in sections:
            if section.heading:
                prefix = "#" * (section.depth + 1)
                parts.append(f"{prefix} {section.heading}")
            if section.body:
                parts.append(section.body)
        return "\n\n".join(parts)

    @staticmethod
    def _extract_title(text: str) -> str:
        """Extract title from first non-empty line."""
        for line in text.split("\n"):
            line = line.strip()
            if line:
                return line[:200]
        return "Untitled Technical Manual"


# ─────────────────────────────────────────────────────────────────────────────
# FAILURE ANALYSIS PARSER
# ─────────────────────────────────────────────────────────────────────────────


class FailureAnalysisParser:
    """
    Parser for failure analysis reports.

    Expected structure:
    - Incident Summary / Overview
    - Timeline / Sequence of Events
    - Root Cause Analysis
    - Failure Mode
    - Corrective Action(s)
    - Recommendations
    - Appendices (test data, telemetry dumps)
    """

    _SECTION_MARKERS = [
        (r"(?i)(?:incident\s+)?summary|overview|abstract", "Summary"),
        (r"(?i)timeline|sequence\s+of\s+events|chronology", "Timeline"),
        (r"(?i)root\s+cause|cause\s+analysis|rca", "Root Cause Analysis"),
        (r"(?i)failure\s+mode|fault\s+analysis", "Failure Mode"),
        (r"(?i)corrective\s+action|remediation|mitigation", "Corrective Actions"),
        (r"(?i)recommendation|suggested\s+action", "Recommendations"),
        (r"(?i)appendix|annex|attachment|supporting\s+data", "Appendix"),
        (r"(?i)conclusion|finding", "Conclusions"),
    ]

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.FAILURE_ANALYSIS

    def parse(self, raw_text: str, title: str = "") -> ParseResult:
        sections = self._extract_failure_sections(raw_text)
        assembled = self._assemble_body(sections)

        has_rca = any("Root Cause" in s.heading for s in sections)
        has_actions = any("Corrective" in s.heading for s in sections)

        return ParseResult(
            title=title or "Failure Analysis Report",
            sections=sections,
            assembled_body=assembled,
            structural_metadata={
                "parser": "failure_analysis",
                "has_root_cause": str(has_rca),
                "has_corrective_actions": str(has_actions),
                "num_sections": str(len(sections)),
            },
        )

    def _extract_failure_sections(self, text: str) -> list[ParsedSection]:
        """Extract known failure report sections using semantic markers."""
        sections: list[ParsedSection] = []
        remaining = text

        # Find each known section marker
        found_markers: list[tuple[int, str, str]] = []
        for pattern, label in self._SECTION_MARKERS:
            for m in re.finditer(pattern, text):
                found_markers.append((m.start(), label, m.group()))

        found_markers.sort(key=lambda x: x[0])

        if not found_markers:
            return [ParsedSection(heading="Full Report", body=text.strip(), depth=0)]

        # Preamble before first marker
        if found_markers[0][0] > 0:
            preamble = text[: found_markers[0][0]].strip()
            if preamble:
                sections.append(ParsedSection(heading="Preamble", body=preamble, depth=0))

        for i, (pos, label, _) in enumerate(found_markers):
            end = found_markers[i + 1][0] if i + 1 < len(found_markers) else len(text)
            # Find end of the header line
            line_end = text.find("\n", pos)
            if line_end == -1:
                line_end = len(text)
            body = text[line_end:end].strip()
            sections.append(ParsedSection(heading=label, body=body, depth=0))

        return sections

    @staticmethod
    def _assemble_body(sections: list[ParsedSection]) -> str:
        parts: list[str] = []
        for s in sections:
            if s.heading:
                parts.append(f"## {s.heading}")
            if s.body:
                parts.append(s.body)
        return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Q&A DOCS PARSER
# ─────────────────────────────────────────────────────────────────────────────


class QADocsParser:
    """
    Parser for Q&A knowledge base documents.

    Handles:
    - Question/Answer pair extraction
    - FAQ-style documents
    - Category groupings
    """

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.QA_DOCS

    def parse(self, raw_text: str, title: str = "") -> ParseResult:
        pairs = self._extract_qa_pairs(raw_text)

        sections = []
        for i, (q, a) in enumerate(pairs):
            sections.append(
                ParsedSection(
                    heading=f"Q{i + 1}: {q[:100]}",
                    body=f"Question: {q}\n\nAnswer: {a}",
                    depth=0,
                )
            )

        assembled = self._assemble_body(sections)

        return ParseResult(
            title=title or "Q&A Document",
            sections=sections,
            assembled_body=assembled or raw_text,
            structural_metadata={
                "parser": "qa_docs",
                "num_qa_pairs": str(len(pairs)),
            },
        )

    @staticmethod
    def _extract_qa_pairs(text: str) -> list[tuple[str, str]]:
        """Extract Q&A pairs from various formats."""
        pairs: list[tuple[str, str]] = []

        # Pattern 1: "Q: ... A: ..."
        qa_pattern = re.compile(
            r"(?:^|\n)\s*(?:Q|Question)\s*[:\.]?\s*(.+?)(?:\n\s*(?:A|Answer)\s*[:\.]?\s*(.+?)(?=\n\s*(?:Q|Question)\s*[:\.]?|\Z))",
            re.DOTALL | re.IGNORECASE,
        )

        for match in qa_pattern.finditer(text):
            q = match.group(1).strip()
            a = match.group(2).strip()
            if q and a:
                pairs.append((q, a))

        if not pairs:
            # Pattern 2: numbered pairs "1. Question ... Answer ..."
            numbered_pattern = re.compile(
                r"(?:^|\n)\s*\d+[.)]\s*(.+?)(?:\n|$)",
                re.MULTILINE,
            )
            lines = [m.group(1).strip() for m in numbered_pattern.finditer(text)]
            # Pair consecutive lines as Q/A
            for i in range(0, len(lines) - 1, 2):
                pairs.append((lines[i], lines[i + 1]))

        return pairs

    @staticmethod
    def _assemble_body(sections: list[ParsedSection]) -> str:
        parts: list[str] = []
        for s in sections:
            if s.heading:
                parts.append(f"## {s.heading}")
            if s.body:
                parts.append(s.body)
        return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# TELEMETRY STORIES PARSER
# ─────────────────────────────────────────────────────────────────────────────


class TelemetryStoriesParser:
    """
    Parser for machine telemetry stories / narratives.

    Handles:
    - Time-stamped event sequences
    - Metric/parameter sections
    - Anomaly markers
    - Sensor reading summaries
    """

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.TELEMETRY_STORIES

    def parse(self, raw_text: str, title: str = "") -> ParseResult:
        sections = self._extract_telemetry_sections(raw_text)
        assembled = self._assemble_body(sections)

        return ParseResult(
            title=title or "Telemetry Story",
            sections=sections,
            assembled_body=assembled,
            structural_metadata={
                "parser": "telemetry_stories",
                "num_sections": str(len(sections)),
            },
        )

    def _extract_telemetry_sections(self, text: str) -> list[ParsedSection]:
        """Extract sections from telemetry narratives."""
        # Look for timestamp-based sections
        timestamp_pattern = re.compile(
            r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)\s*[:\-]?\s*(.*)$",
            re.MULTILINE,
        )

        matches = list(timestamp_pattern.finditer(text))

        if len(matches) >= 2:
            sections: list[ParsedSection] = []
            for i, m in enumerate(matches):
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                body = text[m.end() : end].strip()
                heading = f"[{m.group(1)}] {m.group(2)}".strip()
                sections.append(ParsedSection(heading=heading, body=body, depth=0))
            return sections

        # Fallback to generic section detection
        return [ParsedSection(heading="", body=text.strip(), depth=0)]

    @staticmethod
    def _assemble_body(sections: list[ParsedSection]) -> str:
        parts: list[str] = []
        for s in sections:
            if s.heading:
                parts.append(f"## {s.heading}")
            if s.body:
                parts.append(s.body)
        return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# PROCUREMENT RULES PARSER
# ─────────────────────────────────────────────────────────────────────────────


class ProcurementRulesParser:
    """
    Parser for procurement rules and policy documents.

    Handles:
    - Clause/sub-clause structure
    - Legal references
    - Eligibility criteria
    - Procedure steps
    """

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.PROCUREMENT_RULES

    def parse(self, raw_text: str, title: str = "") -> ParseResult:
        sections = self._extract_clauses(raw_text)
        assembled = self._assemble_body(sections)

        return ParseResult(
            title=title or "Procurement Rules Document",
            sections=sections,
            assembled_body=assembled,
            structural_metadata={
                "parser": "procurement_rules",
                "num_clauses": str(len(sections)),
            },
        )

    def _extract_clauses(self, text: str) -> list[ParsedSection]:
        """Extract clause structure from procurement documents."""
        clause_pattern = re.compile(
            r"^(?:Clause|Rule|Article|Section)\s+(\d+(?:\.\d+)*)\s*[:\.\-]\s*(.*)$",
            re.MULTILINE | re.IGNORECASE,
        )

        matches = list(clause_pattern.finditer(text))

        if not matches:
            return [ParsedSection(heading="", body=text.strip(), depth=0)]

        sections: list[ParsedSection] = []

        # Preamble
        if matches[0].start() > 0:
            preamble = text[: matches[0].start()].strip()
            if preamble:
                sections.append(ParsedSection(heading="Preamble", body=preamble, depth=0))

        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            clause_num = m.group(1)
            clause_title = m.group(2).strip()
            body = text[m.end() : end].strip()
            depth = clause_num.count(".")

            sections.append(
                ParsedSection(
                    heading=f"Clause {clause_num}: {clause_title}",
                    body=body,
                    depth=depth,
                )
            )

        return sections

    @staticmethod
    def _assemble_body(sections: list[ParsedSection]) -> str:
        parts: list[str] = []
        for s in sections:
            prefix = "#" * (s.depth + 1)
            if s.heading:
                parts.append(f"{prefix} {s.heading}")
            if s.body:
                parts.append(s.body)
        return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN NOTES PARSER
# ─────────────────────────────────────────────────────────────────────────────


class AdminNotesParser:
    """
    Parser for administrative notes and memos.

    Handles:
    - Memo header extraction (To, From, Subject, Date)
    - Bullet-point lists
    - Minimal structure
    """

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.ADMIN_NOTES

    def parse(self, raw_text: str, title: str = "") -> ParseResult:
        header, body = self._extract_memo_header(raw_text)

        sections = [ParsedSection(heading="", body=body.strip(), depth=0)]

        return ParseResult(
            title=title or header.get("subject", "Admin Note"),
            sections=sections,
            assembled_body=body,
            structural_metadata={
                "parser": "admin_notes",
                **{k: v for k, v in header.items() if v},
            },
        )

    @staticmethod
    def _extract_memo_header(text: str) -> tuple[dict[str, str], str]:
        """Extract memo header fields (To, From, Subject, Date) from text."""
        header: dict[str, str] = {}
        body_start = 0

        header_patterns = {
            "to": r"(?i)^To\s*:\s*(.+?)$",
            "from": r"(?i)^From\s*:\s*(.+?)$",
            "subject": r"(?i)^(?:Subject|Re|Regarding)\s*:\s*(.+?)$",
            "date": r"(?i)^Date\s*:\s*(.+?)$",
        }

        for line_num, line in enumerate(text.split("\n")):
            matched = False
            for key, pattern in header_patterns.items():
                m = re.match(pattern, line.strip())
                if m:
                    header[key] = m.group(1).strip()
                    matched = True
                    break

            if not matched and line.strip() and line_num > 0:
                # Body starts at first non-header, non-empty line
                body_start = text.find(line)
                break

        body = text[body_start:].strip() if body_start > 0 else text
        return header, body


# ─────────────────────────────────────────────────────────────────────────────
# PARSER REGISTRY
# ─────────────────────────────────────────────────────────────────────────────


class ParserRegistry:
    """
    Registry mapping DataSourceType to parser instances.

    Provides type-safe parser lookup for the ingestion pipeline.
    """

    def __init__(self) -> None:
        self._parsers: dict[DataSourceType, DocumentParser] = {
            DataSourceType.TECHNICAL_MANUAL: TechnicalManualParser(),
            DataSourceType.FAILURE_ANALYSIS: FailureAnalysisParser(),
            DataSourceType.QA_DOCS: QADocsParser(),
            DataSourceType.TELEMETRY_STORIES: TelemetryStoriesParser(),
            DataSourceType.PROCUREMENT_RULES: ProcurementRulesParser(),
            DataSourceType.ADMIN_NOTES: AdminNotesParser(),
        }

    def get_parser(self, source_type: DataSourceType) -> DocumentParser:
        """Get parser by data source type. Hard-fails if not registered."""
        parser = self._parsers.get(source_type)
        if parser is None:
            raise IngestionError(
                message=f"No parser registered for source type: {source_type.value}",
                context={"source_type": source_type.value},
            )
        return parser

    def get_parser_for_source_system(
        self, source_system: str
    ) -> DocumentParser | None:
        """Look up parser via source system mapping. Returns None if unmapped."""
        from app.ingestion.config import DEFAULT_SOURCE_SYSTEM_MAPPINGS

        for mapping in DEFAULT_SOURCE_SYSTEM_MAPPINGS:
            if mapping.source_system == source_system:
                return self.get_parser(mapping.data_source_type)
        return None


# Module-level singleton
parser_registry = ParserRegistry()
