"""
Query Normalization
====================

Standardizes user queries before routing them to indices.
Ensures uniform casing, whitespace, and Unicode representations
so keyword indices and tokenizers perform deterministically.
"""

from __future__ import annotations

import re
import unicodedata

from app.core.logging import get_logger

logger = get_logger(__name__)


class QueryNormalizer:
    """
    Normalizes a user query.
    
    Steps:
    1. Unicode NFC normalization
    2. Lowercase conversion (for keyword token matching)
    3. Collapse multiple spaces and newlines
    4. Strip leading/trailing whitespace
    """

    @staticmethod
    def normalize(query: str) -> str:
        """
        Produce a normalized query string.
        """
        # 1. Unicode NFC normalization (handles distinct char representations)
        normalized = unicodedata.normalize("NFC", query)
        
        # 2. Lowercase (optional depending on OpenSearch analyzer, but safer here)
        normalized = normalized.lower()
        
        # 3. Collapse whitespace and newlines
        normalized = re.sub(r"\s+", " ", normalized)
        
        # 4. Strip
        normalized = normalized.strip()

        logger.debug(
            "query_normalized",
            original_length=len(query),
            normalized_length=len(normalized),
        )
        
        return normalized
