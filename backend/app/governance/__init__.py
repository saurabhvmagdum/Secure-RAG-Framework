"""
Governance package — Data classification, governed checkpoints, controlled vocabulary.

Phase 2: Production implementations with source system mapping,
content-based classification, and policy engine integration.
"""

from app.governance.classification import (
    ClassificationEngine,
    DataClassificationRule,
    DefaultClassificationEngine,
    DEFAULT_CLASSIFICATION_RULES,
)
from app.governance.checkpoint import governance_checkpoint
from app.governance.vocabulary import (
    ControlledVocabularyRegistry,
    vocabulary_registry,
)

__all__ = [
    "ClassificationEngine",
    "DataClassificationRule",
    "DefaultClassificationEngine",
    "DEFAULT_CLASSIFICATION_RULES",
    "governance_checkpoint",
    "ControlledVocabularyRegistry",
    "vocabulary_registry",
]
