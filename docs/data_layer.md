Tri-index foundation schema
Common document envelope
text
Document:
  doc_id: string              # Stable UUID across indices
  title: string
  body: string                # Full original text
  created_at: datetime
  updated_at: datetime
  source_system: string       # e.g., "EDMS", "TelemetryDB"
  metadata:
    domain_tag: string        # Controlled vocabulary, e.g., "propulsion", "procurement"
    sensitivity_level: string # e.g., "PUBLIC", "INTERNAL", "CONFIDENTIAL", "SECRET"
    version: string           # Source document version or ingestion batch ID
    origin: string            # Repository path / URL / system identifier
Keyword Index (BM25)
text
KeywordIndexDocument:
  doc_id: string              # FK -> Document.doc_id
  chunk_id: string            # Unique per chunk
  section_path: string        # e.g., "Chapter 3 > Section 3.2"
  text_chunk: string
  tokens: list[string]        # Preprocessed tokens
  bm25_vector: list[float]    # Optional precomputed term weights
  metadata: Document.metadata
  indexing:
    shard_id: string
    checksum: string          # For integrity verification
Processing logic: normalized text is tokenized, stop-words removed, stemming/lemmatization applied, and chunks written into a dedicated BM25-capable lexical engine keyed by chunk_id.

Semantic Index (Domain-Specific Embedding Model)
text
SemanticIndexDocument:
  doc_id: string              # FK -> Document.doc_id
  chunk_id: string
  text_chunk: string
  embedding: list[float]      # Produced by on-prem domain-specific encoder
  embedding_model_id: string  # e.g., "isro-encoder-v2"
  metadata: Document.metadata
  similarity_metric: string   # "cosine" | "dot_product"
Processing logic: chunks are fed through quantized, on-prem embedding models; embeddings are stored in a vector DB partitioned by sensitivity level and domain_tag; all similarity computations occur in-cluster.

Knowledge Graph Index (Entity-Relationship Mapping)
text
GraphNode:
  node_id: string
  doc_id: string              # FK -> Document.doc_id
  chunk_id: string | null
  label: string               # e.g., "Subsystem", "Component", "FailureMode", "ProcurementRule"
  properties:
    name: string
    aliases: list[string]
    domain_tag: string
    sensitivity_level: string
    origin: string
    version: string

GraphEdge:
  edge_id: string
  from_node_id: string
  to_node_id: string
  relation_type: string       # e.g., "PART_OF", "CAUSES", "GOVERNS", "DERIVED_FROM"
  properties:
    confidence: float         # Extraction confidence
    created_at: datetime
    provenance_chunk_id: string
Processing logic: NER and relation extraction (on-prem models) run over chunks to derive nodes and edges; graph DB is used for path queries, neighborhood expansion, and rule-based traversals under RBAC constraints.

Ingestion pipeline contracts
Normalization
python
from typing import Protocol, Iterable
from datetime import datetime

class RawDocument(TypedDict):
    external_id: str
    title: str
    body: str
    created_at: datetime
    updated_at: datetime
    source_system: str
    raw_metadata: dict

class NormalizedDocument(TypedDict):
    doc_id: str
    title: str
    body: str
    created_at: datetime
    updated_at: datetime
    source_system: str
    metadata: dict  # domain_tag, sensitivity_level, version, origin

class Normalizer(Protocol):
    def __call__(self, raw: RawDocument) -> NormalizedDocument: ...
Contract: Normalizers must be deterministic, stateless, and must not enrich or infer metadata fields outside the approved schema; sensitivity_level is derived via rules engine, not free-text.

Chunking
python
class Chunk(TypedDict):
    doc_id: str
    chunk_id: str
    section_path: str
    text: str
    metadata: dict  # propagated from NormalizedDocument

class Chunker(Protocol):
    def __call__(self, doc: NormalizedDocument) -> Iterable[Chunk]: ...
Contract: Chunkers must respect token/char limits per backend (BM25, embeddings, LLM), align with semantic boundaries where possible, and preserve section_path for traceability.

Metadata tagging
python
class MetadataTagger(Protocol):
    def __call__(self, raw: RawDocument) -> dict: ...
Rules:

domain_tag must resolve from a central registry keyed by source_system and document type.

sensitivity_level must be computed using classification policies (e.g., content regex rules, ownership, and source labels).

version must follow source_version or an ingestion sequence; no guessed values.

origin must uniquely identify repository/location and remain stable across re-ingestions.

Governance data model
RBAC schemas
text
Principal:
  principal_id: string        # user or service ID
  type: string                # "USER" | "SERVICE"
  roles: list[string]         # e.g., ["RAG_USER", "RAG_ADMIN"]

Role:
  role_id: string
  permissions: list[PermissionRef]

Permission:
  permission_id: string
  action: string              # "READ_DOC" | "WRITE_INDEX" | "RUN_QUERY" | "VIEW_AUDIT"
  resource: string            # "DOC:*" | "INDEX:SEMANTIC" | "GRAPH:*"
  constraints:
    max_sensitivity_level: string
    allowed_domain_tags: list[string]
Enforcement: All read/write to indices and graph DB passes through a policy engine that evaluates principal, action, resource, and classification constraints before allowing operations.

Data classification and encryption rules
text
DataClassificationRule:
  classification: string      # "PUBLIC" | "INTERNAL" | "CONFIDENTIAL" | "SECRET"
  encryption_at_rest: string  # "AES-256-GCM"
  encryption_in_transit: string  # "TLS1.3"
  key_scope: string           # "per-tenant" | "per-domain" | "global"
  retention_policy_days: int
  allowed_indices:
    - "keyword"
    - "semantic"
    - "graph"
Encryption at rest: all index files, graph stores, and logs reside on encrypted volumes; application-level encryption keys are managed via on-prem KMS or HSM.

Encryption in transit: all in-cluster RPCs (UI ↔ API ↔ retrieval ↔ DBs) use mutual TLS with client certs pinned and rotated according to governance policy.

Audit logging formats
json
{
  "event_id": "uuid",
  "timestamp": "2026-04-04T14:00:00Z",
  "principal_id": "user123",
  "principal_type": "USER",
  "action": "RAG_QUERY_EXECUTED",
  "resource": "RAG_PIPELINE",
  "request_id": "corr-uuid",
  "correlation_ids": ["retrieval-uuid", "verification-uuid"],
  "query": {
    "text": "What were the root causes of anomaly X?",
    "sensitivity_max": "INTERNAL"
  },
  "evidence": {
    "doc_ids": ["doc-1", "doc-2"],
    "indices_used": ["keyword", "semantic", "graph"]
  },
  "verification": {
    "confidence_score": 0.87,
    "threshold": 0.8,
    "route": "HIGH_CONFIDENCE"
  },
  "network": {
    "client_ip": "10.0.1.5"
  },
  "decision": "ALLOW"
}
Logs are append-only, stored in a write-once medium, and periodically exported (within the air-gapped environment) for security analytics and compliance reporting.