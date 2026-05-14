"""
Ingestion package — Document normalization, chunking, metadata tagging,
source-specific parsing, and pipeline orchestration.
"""

from app.ingestion.normalizer import DefaultNormalizer, Normalizer
from app.ingestion.chunker import DefaultChunker, Chunker
from app.ingestion.tagger import DefaultMetadataTagger, MetadataTagger
from app.ingestion.parsers import ParserRegistry, parser_registry
from app.ingestion.pipeline import IngestionPipeline, IngestionResult, BatchIngestionResult

__all__ = [
    "Normalizer",
    "DefaultNormalizer",
    "Chunker",
    "DefaultChunker",
    "MetadataTagger",
    "DefaultMetadataTagger",
    "ParserRegistry",
    "parser_registry",
    "IngestionPipeline",
    "IngestionResult",
    "BatchIngestionResult",
]
