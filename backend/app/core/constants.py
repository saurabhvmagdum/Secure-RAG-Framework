"""
System-Wide Constants
=====================

All constants used across the framework. No magic strings in business logic.
"""

from __future__ import annotations

# ── Application Identity ─────────────────────────────────────────────────────
APP_NAME: str = "isro-rag-framework"
APP_VERSION: str = "0.1.0"

# ── Network Isolation ────────────────────────────────────────────────────────
# These constants exist to make the air-gap guarantee grep-able and auditable.
ALLOW_NETWORK_EGRESS: bool = False
ALLOW_NETWORK_INGRESS: bool = False
ALLOWED_EXTERNAL_HOSTS: list[str] = []  # Must remain empty — enforced at infra level

# ── Approved Metadata Fields ─────────────────────────────────────────────────
# Per .antigravityrules — no additional fields allowed without governance approval.
APPROVED_METADATA_FIELDS: frozenset[str] = frozenset({
    "domain_tag",
    "sensitivity_level",
    "version",
    "origin",
})

# ── Sensitivity Levels ───────────────────────────────────────────────────────
SENSITIVITY_LEVELS: list[str] = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "SECRET"]
SENSITIVITY_HIERARCHY: dict[str, int] = {
    "PUBLIC": 0,
    "INTERNAL": 1,
    "CONFIDENTIAL": 2,
    "SECRET": 3,
}

# ── Index Types ──────────────────────────────────────────────────────────────
INDEX_TYPE_KEYWORD: str = "keyword"
INDEX_TYPE_SEMANTIC: str = "semantic"
INDEX_TYPE_GRAPH: str = "graph"
ALL_INDEX_TYPES: frozenset[str] = frozenset({
    INDEX_TYPE_KEYWORD,
    INDEX_TYPE_SEMANTIC,
    INDEX_TYPE_GRAPH,
})

# ── Routing Decision Constants ───────────────────────────────────────────────
ROUTE_HIGH_CONFIDENCE: str = "HIGH_CONFIDENCE"
ROUTE_FALLBACK_PARTIAL: str = "FALLBACK_PARTIAL"
ROUTE_BLOCKED: str = "BLOCKED"

# ── Verification Loop ───────────────────────────────────────────────────────
DEFAULT_MAX_VERIFICATION_ITERATIONS: int = 3
DEFAULT_K_PRIMARY_CHUNKS: int = 10

# ── Encryption Standards ────────────────────────────────────────────────────
ENCRYPTION_AT_REST_ALGORITHM: str = "AES-256-GCM"
ENCRYPTION_IN_TRANSIT_PROTOCOL: str = "TLS1.3"

# ── Audit Actions ───────────────────────────────────────────────────────────
AUDIT_ACTION_QUERY_SUBMITTED: str = "RAG_QUERY_SUBMITTED"
AUDIT_ACTION_QUERY_EXECUTED: str = "RAG_QUERY_EXECUTED"
AUDIT_ACTION_RETRIEVAL_COMPLETE: str = "RETRIEVAL_COMPLETE"
AUDIT_ACTION_VERIFICATION_COMPLETE: str = "VERIFICATION_COMPLETE"
AUDIT_ACTION_GENERATION_COMPLETE: str = "GENERATION_COMPLETE"
AUDIT_ACTION_INDEX_WRITE: str = "INDEX_WRITE"
AUDIT_ACTION_AUTH_SUCCESS: str = "AUTH_SUCCESS"
AUDIT_ACTION_AUTH_FAILURE: str = "AUTH_FAILURE"
AUDIT_ACTION_ACCESS_DENIED: str = "ACCESS_DENIED"
AUDIT_ACTION_INGESTION_COMPLETE: str = "INGESTION_COMPLETE"

# ── Governance Checkpoints ──────────────────────────────────────────────────
# Matches .antigravityrules required_checkpoints
CHECKPOINT_INGESTION_PRE_NORMALIZATION: str = "ingestion.pre_normalization"
CHECKPOINT_INGESTION_POST_CHUNKING: str = "ingestion.post_chunking"
CHECKPOINT_INDEXING_KEYWORD_WRITE: str = "indexing.keyword_write"
CHECKPOINT_INDEXING_SEMANTIC_WRITE: str = "indexing.semantic_write"
CHECKPOINT_INDEXING_GRAPH_WRITE: str = "indexing.graph_write"
CHECKPOINT_RETRIEVAL_PRE_HYBRID_MERGE: str = "retrieval.pre_hybrid_merge"
CHECKPOINT_VERIFICATION_LOOP_ITERATION: str = "verification.loop_iteration"
CHECKPOINT_GENERATION_RESPONSE_DISPATCH: str = "generation.response_dispatch"

ALL_GOVERNANCE_CHECKPOINTS: frozenset[str] = frozenset({
    CHECKPOINT_INGESTION_PRE_NORMALIZATION,
    CHECKPOINT_INGESTION_POST_CHUNKING,
    CHECKPOINT_INDEXING_KEYWORD_WRITE,
    CHECKPOINT_INDEXING_SEMANTIC_WRITE,
    CHECKPOINT_INDEXING_GRAPH_WRITE,
    CHECKPOINT_RETRIEVAL_PRE_HYBRID_MERGE,
    CHECKPOINT_VERIFICATION_LOOP_ITERATION,
    CHECKPOINT_GENERATION_RESPONSE_DISPATCH,
})
