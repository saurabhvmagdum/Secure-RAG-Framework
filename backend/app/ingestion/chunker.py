"""
Document Chunker
=================

Splits NormalizedDocument into Chunks while:
- Respecting section heading boundaries
- Preserving section_path for traceability
- Maintaining char/token limits per backend
- Overlapping chunks for context continuity
- Propagating governed metadata to every chunk

Governance checkpoint: ingestion.post_chunking
"""

from __future__ import annotations

import re
import uuid
from typing import Iterable, Protocol, runtime_checkable

from app.core.exceptions import IngestionError
from app.core.logging import get_logger
from app.governance.checkpoint import governance_checkpoint
from app.ingestion.config import ChunkingSettings
from app.models.document import Chunk, NormalizedDocument

logger = get_logger(__name__)

# UUID5 namespace for deterministic chunk IDs
_CHUNK_ID_NAMESPACE = uuid.UUID("b2c3d4e5-f6a7-8901-bcde-f12345678901")


@runtime_checkable
class Chunker(Protocol):
    """
    Protocol for document chunking.

    Contract:
    - Chunks must respect token/char limits for each backend
    - Chunks should align with semantic boundaries
    - section_path must be preserved for traceability
    - Metadata must be propagated from parent NormalizedDocument
    - chunk_id must be unique and deterministic
    """

    def chunk(self, document: NormalizedDocument) -> Iterable[Chunk]:
        """Split a normalized document into chunks."""
        ...

    @property
    def max_chunk_chars(self) -> int:
        """Maximum characters per chunk."""
        ...

    @property
    def chunk_overlap_chars(self) -> int:
        """Character overlap between consecutive chunks."""
        ...


class DefaultChunker:
    """
    Production document chunker.

    Strategy:
    1. Parse document into sections using heading patterns
    2. Within each section, split into paragraph-aware chunks
    3. Apply overlap between consecutive chunks
    4. Generate deterministic chunk_id via UUID5(doc_id + chunk_index)
    5. Propagate governed metadata from parent NormalizedDocument
    6. Enforce min/max chunk size constraints
    """

    def __init__(self, settings: ChunkingSettings | None = None) -> None:
        self._settings = settings or ChunkingSettings()
        self._heading_patterns = [
            re.compile(p) for p in self._settings.section_heading_patterns
        ]

    @property
    def max_chunk_chars(self) -> int:
        return self._settings.max_chunk_chars

    @property
    def chunk_overlap_chars(self) -> int:
        return self._settings.chunk_overlap_chars

    @governance_checkpoint(
        "ingestion.post_chunking", require_principal=False
    )
    def chunk(self, document: NormalizedDocument) -> list[Chunk]:
        """
        Split a normalized document into governed chunks.

        Enforces governance checkpoint. Hard-fails if document body is empty.
        """
        if not document.body.strip():
            raise IngestionError(
                message="Cannot chunk document with empty body",
                context={"doc_id": document.doc_id},
            )

        # Step 1: Parse into sections
        sections = self._parse_sections(document.body)

        # Step 2: Generate chunks from sections
        raw_chunks = self._split_sections_into_chunks(sections)

        # Step 3: Build typed Chunk objects with metadata propagation
        chunks: list[Chunk] = []
        for idx, (section_path, text) in enumerate(raw_chunks):
            chunk_id = self._generate_chunk_id(document.doc_id, idx)

            chunk = Chunk(
                doc_id=document.doc_id,
                chunk_id=chunk_id,
                section_path=section_path,
                text=text,
                char_count=len(text),
                token_count=self._estimate_tokens(text),
                chunk_index=idx,
                metadata=document.metadata,
            )
            chunks.append(chunk)

        logger.info(
            "document_chunked",
            doc_id=document.doc_id,
            total_chunks=len(chunks),
            total_chars=sum(c.char_count for c in chunks),
            sections_found=len(sections),
        )

        return chunks

    def _parse_sections(self, body: str) -> list[tuple[str, str]]:
        """
        Parse document body into (section_path, section_text) pairs.

        Identifies section headings using configured patterns.
        Text before the first heading is assigned to root section "".
        """
        lines = body.split("\n")
        sections: list[tuple[str, str]] = []
        current_heading = ""
        current_lines: list[str] = []
        heading_stack: list[str] = []

        for line in lines:
            is_heading = False
            for pattern in self._heading_patterns:
                if pattern.match(line.strip()):
                    is_heading = True
                    break

            if is_heading:
                # Flush previous section
                if current_lines:
                    section_text = "\n".join(current_lines).strip()
                    if section_text:
                        sections.append((current_heading, section_text))
                    current_lines = []

                # Update heading stack
                heading_text = line.strip()
                heading_depth = self._get_heading_depth(heading_text)

                # Trim stack to current depth
                heading_stack = heading_stack[:heading_depth]
                heading_stack.append(self._clean_heading(heading_text))

                current_heading = " > ".join(heading_stack)
            else:
                current_lines.append(line)

        # Flush last section
        if current_lines:
            section_text = "\n".join(current_lines).strip()
            if section_text:
                sections.append((current_heading, section_text))

        # If no sections found, treat entire body as one section
        if not sections:
            sections = [("", body.strip())]

        return sections

    def _split_sections_into_chunks(
        self, sections: list[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        """
        Split section text into chunks with overlap.

        Prefers paragraph boundaries, then sentence boundaries, then hard character split.
        """
        result: list[tuple[str, str]] = []

        for section_path, section_text in sections:
            if len(section_text) <= self._settings.max_chunk_chars:
                # Section fits in one chunk
                if len(section_text) >= self._settings.min_chunk_chars:
                    result.append((section_path, section_text))
                elif result:
                    # Merge small section into previous chunk
                    prev_path, prev_text = result[-1]
                    result[-1] = (prev_path, prev_text + "\n\n" + section_text)
                else:
                    result.append((section_path, section_text))
                continue

            # Split into paragraphs first
            paragraphs = re.split(r"\n\s*\n", section_text)
            current_chunk_parts: list[str] = []
            current_chunk_len = 0

            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue

                para_len = len(para)

                if (
                    current_chunk_len + para_len + 1
                    <= self._settings.max_chunk_chars
                ):
                    current_chunk_parts.append(para)
                    current_chunk_len += para_len + 1
                else:
                    # Flush current chunk
                    if current_chunk_parts:
                        chunk_text = "\n\n".join(current_chunk_parts)
                        result.append((section_path, chunk_text))

                        # Create overlap from end of previous chunk
                        if self._settings.chunk_overlap_chars > 0:
                            overlap = chunk_text[-self._settings.chunk_overlap_chars:]
                            current_chunk_parts = [overlap, para]
                            current_chunk_len = len(overlap) + para_len + 1
                        else:
                            current_chunk_parts = [para]
                            current_chunk_len = para_len
                    else:
                        # Single paragraph is too large — split by sentences
                        sentence_chunks = self._split_large_text(para)
                        for sc in sentence_chunks:
                            result.append((section_path, sc))
                        current_chunk_parts = []
                        current_chunk_len = 0

            # Flush remaining
            if current_chunk_parts:
                chunk_text = "\n\n".join(current_chunk_parts)
                if len(chunk_text) >= self._settings.min_chunk_chars:
                    result.append((section_path, chunk_text))
                elif result:
                    # Merge trailing small content into previous chunk
                    prev_path, prev_text = result[-1]
                    merged = prev_text + "\n\n" + chunk_text
                    if len(merged) <= self._settings.max_chunk_chars * 1.2:
                        result[-1] = (prev_path, merged)
                    else:
                        result.append((section_path, chunk_text))
                else:
                    result.append((section_path, chunk_text))

        return result

    def _split_large_text(self, text: str) -> list[str]:
        """
        Split a large text block that exceeds max_chunk_chars.

        Prefers sentence boundaries. Falls back to hard character split.
        """
        chunks: list[str] = []
        max_chars = self._settings.max_chunk_chars

        if self._settings.respect_sentence_boundaries:
            sentences = re.split(r"(?<=[.!?])\s+", text)
            current_parts: list[str] = []
            current_len = 0

            for sentence in sentences:
                s_len = len(sentence)
                if current_len + s_len + 1 <= max_chars:
                    current_parts.append(sentence)
                    current_len += s_len + 1
                else:
                    if current_parts:
                        chunks.append(" ".join(current_parts))
                    if s_len > max_chars:
                        # Force-split very long sentence
                        for i in range(0, s_len, max_chars):
                            chunks.append(sentence[i : i + max_chars])
                        current_parts = []
                        current_len = 0
                    else:
                        current_parts = [sentence]
                        current_len = s_len

            if current_parts:
                chunks.append(" ".join(current_parts))
        else:
            # Hard character split
            for i in range(0, len(text), max_chars):
                chunks.append(text[i : i + max_chars])

        return chunks

    @staticmethod
    def _generate_chunk_id(doc_id: str, chunk_index: int) -> str:
        """Generate deterministic chunk_id from doc_id + chunk_index."""
        seed = f"{doc_id}:chunk:{chunk_index}"
        return str(uuid.uuid5(_CHUNK_ID_NAMESPACE, seed))

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """
        Approximate token count using whitespace + punctuation heuristic.

        Rough estimate: ~4 chars per token for English technical text.
        """
        return max(1, len(text) // 4)

    @staticmethod
    def _get_heading_depth(heading: str) -> int:
        """Determine heading depth for section hierarchy."""
        # Markdown headings
        md_match = re.match(r"^(#{1,6})\s+", heading)
        if md_match:
            return len(md_match.group(1)) - 1

        # Numbered sections (1.2.3)
        num_match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", heading)
        if num_match:
            groups = [g for g in num_match.groups() if g is not None]
            return len(groups) - 1

        return 0

    @staticmethod
    def _clean_heading(heading: str) -> str:
        """Clean heading text for section_path display."""
        heading = re.sub(r"^#{1,6}\s+", "", heading)
        heading = heading.strip()
        return heading[:100]  # Truncate very long headings
