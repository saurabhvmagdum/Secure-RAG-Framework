# Ingestion Flow & Tri-Index Strategy

## Overview

The ISRO RAG Framework ingestion pipeline transforms raw documents from 6 supported data source types into governed, searchable knowledge distributed across 3 complementary indices. Every step is governed by checkpoints, classification rules, and audit logging.

---

## Data Source Types

| Source Type | Parser | Domain Default | Example Source Systems |
|---|---|---|---|
| Technical Manuals | `TechnicalManualParser` | varies by subsystem | EDMS, EDMS-Propulsion, EDMS-Avionics |
| Failure Analysis Reports | `FailureAnalysisParser` | `failure_analysis` | FailureDB |
| Q&A Docs | `QADocsParser` | `general` | QAKnowledgeBase, QualityDB |
| Telemetry Stories | `TelemetryStoriesParser` | `telemetry` | TelemetryDB, GroundStation |
| Procurement Rules | `ProcurementRulesParser` | `procurement` | ProcurementPortal |
| Admin Notes | `AdminNotesParser` | `administration` | AdminDMS |

---

## Pipeline Flow

```
                     ┌──────────────────────────────────────────────────┐
                     │              Ingestion Pipeline                  │
                     │                                                  │
  RawDocument ─────► │  1. Source Parser (structural extraction)        │
                     │  2. Normalizer (UUID, text cleanup, metadata)    │
                     │     └─ [CHECKPOINT: ingestion.pre_normalization] │
                     │     └─ MetadataTagger                           │
                     │         ├─ VocabularyRegistry → domain_tag      │
                     │         ├─ ClassificationEngine → sensitivity    │
                     │         ├─ Version extraction                    │
                     │         └─ Origin derivation                     │
                     │  3. Chunker (section-aware splitting)            │
                     │     └─ [CHECKPOINT: ingestion.post_chunking]     │
                     │  4. Tri-Index Writes                             │
                     │     ├─ Keyword Index (OpenSearch)                │
                     │     │   └─ [CHECKPOINT: indexing.keyword_write]  │
                     │     ├─ Semantic Index (Qdrant)                   │
                     │     │   └─ [CHECKPOINT: indexing.semantic_write] │
                     │     └─ Graph Index (Neo4j)                       │
                     │         └─ [CHECKPOINT: indexing.graph_write]    │
                     │  5. Audit Event Emission                         │
                     └──────────────────────────────────────────────────┘
```

---

## Stage 1: Source-Specific Parsing

Each data source type has a dedicated parser that extracts structural sections from the raw text without modifying metadata. Parsers are stateless and deterministic.

**Parser selection:** The `ParserRegistry` maps `source_system` → `DataSourceType` → `DocumentParser` using the governed `SourceSystemMapping` table in `app/ingestion/config.py`.

**Structural output:** Parsers produce a `ParseResult` containing:
- Extracted `sections` with heading and depth
- `assembled_body` with section markers for the chunker
- `structural_metadata` (e.g., `num_sections`, `has_root_cause`) — NOT propagated to DocumentMetadata

**Parser behavior:** If no parser is registered for a source system, the document passes through unmodified. If a parser fails, the document passes through unmodified (non-fatal fallback).

---

## Stage 2: Normalization

The `DefaultNormalizer` transforms `RawDocument` → `NormalizedDocument`:

1. **Validation** — Title presence, body non-empty, size limits, timestamp consistency
2. **UUID5 doc_id** — Deterministic from `source_system:external_id` (idempotent re-ingestion)
3. **Text normalization** — Unicode NFC, control char removal, whitespace collapse, paragraph preservation
4. **Metadata tagging** — Via `DefaultMetadataTagger`:

### Metadata Derivation

| Field | Resolution Order | Fail Behavior |
|---|---|---|
| `domain_tag` | Source mapping → prefix match → raw_metadata → doc type → GENERAL | GENERAL default |
| `sensitivity_level` | Content scan → raw_metadata → source mapping → engine → max(all) | SECRET if unresolvable |
| `version` | raw_metadata["version"] → raw_metadata["document_version"] → updated_at timestamp | batch-{timestamp} |
| `origin` | `{source_system}/{external_id}` | Always derivable |

### Content-Based Sensitivity Escalation

The tagger scans the first 5000 chars of title + body against governance-approved regex patterns:

- **SECRET:** `TOP SECRET`, `CLASSIFIED`, `ORBITAL PARAMETERS`, `LAUNCH CODES`, etc.
- **CONFIDENTIAL:** `CONFIDENTIAL`, `FAILURE MODE`, `ROOT CAUSE ANALYSIS`, `ANOMALY REPORT`, etc.
- **INTERNAL:** `INTERNAL USE ONLY`, `NOT FOR DISTRIBUTION`, `DRAFT`, etc.

Content analysis can only **escalate** — never downgrade the sensitivity from the source baseline.

---

## Stage 3: Chunking

The `DefaultChunker` splits `NormalizedDocument` → `list[Chunk]`:

1. **Section detection** — Identifies headings using configurable patterns (markdown, numbered, Chapter/Section/Appendix markers)
2. **Paragraph-aware splitting** — Respects paragraph boundaries within sections
3. **Sentence fallback** — Falls back to sentence boundaries for oversized paragraphs
4. **Overlap** — Configurable character overlap between consecutive chunks (default: 200 chars)
5. **Min/max enforcement** — Small chunks are merged into previous; large chunks are force-split
6. **Metadata propagation** — Every chunk inherits the full `DocumentMetadata` from its parent
7. **Deterministic chunk_id** — UUID5 from `doc_id:chunk:{chunk_index}`

### Chunking Configuration

| Parameter | Default | Description |
|---|---|---|
| `max_chunk_chars` | 1500 | Maximum characters per chunk |
| `chunk_overlap_chars` | 200 | Character overlap between chunks |
| `min_chunk_chars` | 100 | Minimum chunk size (smaller chunks are merged) |
| `respect_sentence_boundaries` | `true` | Prefer sentence boundary splits |
| `respect_paragraph_boundaries` | `true` | Prefer paragraph boundary splits |

---

## Stage 4: Tri-Index Writes

The `IndexingOrchestrator` fans out chunk writes to all three indices. Each index write is independent — a failure in one does NOT block others.

### Keyword Index (OpenSearch)

- **Index naming:** `isro-rag-kw-{sensitivity}-{domain}` (sensitivity + domain partitioning)
- **Integrity:** SHA-256 checksum per indexed document
- **Classification:** SECRET data is **excluded** from keyword index (no cleartext tokens)
- **Governance:** `@governance_checkpoint("indexing.keyword_write")`

### Semantic Index (Qdrant)

- **Collection naming:** `isro-rag-sem-{sensitivity}` (sensitivity-based partitioning)
- **Embedding:** On-prem domain-specific encoder (Phase 2 skeleton: zero vector placeholder)
- **Provenance:** `embedding_model_id` tracked in every vector payload
- **Metadata payload:** Full governed metadata for filtered retrieval
- **Governance:** `@governance_checkpoint("indexing.semantic_write")`

### Graph Index (Neo4j)

- **Entity extraction:** Rule-based pattern matching (deterministic, no ML NER)
- **Entity types:** MISSION, COMPONENT, SYSTEM, PARAMETER, ANOMALY, FACILITY
- **Relations:** Co-occurrence inference using governance-approved templates
- **Provenance:** Every node/edge tracks `doc_id`, `chunk_id`, `sensitivity`
- **Governance:** `@governance_checkpoint("indexing.graph_write")`

---

## Classification & Index Eligibility

| Sensitivity Level | Keyword | Semantic | Graph | Encryption | Key Scope |
|---|---|---|---|---|---|
| PUBLIC | ✅ | ✅ | ✅ | AES-256-GCM | global |
| INTERNAL | ✅ | ✅ | ✅ | AES-256-GCM | per-domain |
| CONFIDENTIAL | ✅ | ✅ | ✅ | AES-256-GCM | per-domain |
| SECRET | ❌ | ✅ | ✅ | AES-256-GCM | per-tenant |

---

## Governance Checkpoints

All 5 ingestion/indexing checkpoints from `.antigravityrules` are enforced:

| Checkpoint | Stage | Behavior on Failure |
|---|---|---|
| `ingestion.pre_normalization` | Normalizer entry | Hard fail — document rejected |
| `ingestion.post_chunking` | Chunker entry | Hard fail — chunks not produced |
| `indexing.keyword_write` | KeywordIndexWriter | Hard fail for that index only |
| `indexing.semantic_write` | SemanticIndexWriter | Hard fail for that index only |
| `indexing.graph_write` | GraphIndexWriter | Hard fail for that index only |

Each checkpoint:
1. Logs entry with correlation ID
2. Evaluates PolicyEngine (when principal is available)
3. Executes the wrapped function
4. Logs exit with outcome
5. Emits audit event (GOVERNANCE_CHECKPOINT action)

---

## Audit Trail

Every ingestion produces the following audit events:

| Event | Action | When |
|---|---|---|
| Document ingestion | `INGESTION_COMPLETE` | After full pipeline |
| Governance checkpoint | `GOVERNANCE_CHECKPOINT` | At each checkpoint |
| Keyword index write | `INDEX_WRITE` | After OpenSearch write |
| Semantic index write | `INDEX_WRITE` | After Qdrant write |
| Graph index write | `INDEX_WRITE` | After Neo4j write |
| Tri-index summary | `INDEX_WRITE` | Orchestrator consolidated event |

---

## API Endpoints

### POST `/api/v1/ingest`

Ingest a single document through the full pipeline.

```json
{
  "external_id": "DOC-2024-001",
  "title": "PSLV-C60 Stage 4 Anomaly Report",
  "body": "...",
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-16T14:30:00Z",
  "source_system": "FailureDB",
  "raw_metadata": {
    "version": "2.1",
    "sensitivity_level": "CONFIDENTIAL"
  }
}
```

### POST `/api/v1/ingest/batch`

Ingest up to 100 documents in a single batch. Per-document error isolation.

---

## Error Handling

| Error Type | Behavior | Audit |
|---|---|---|
| Validation failure | Hard fail — document rejected | `INGESTION_COMPLETE` with `ERROR` |
| Metadata schema violation | Hard fail — document rejected | `INGESTION_COMPLETE` with `ERROR` |
| Vocabulary violation | Hard fail — invalid domain_tag | `INGESTION_COMPLETE` with `ERROR` |
| Classification error | Hard fail — cannot determine sensitivity | `INGESTION_COMPLETE` with `ERROR` |
| Index write failure | Fail for that index only — others continue | Per-index audit event |
| Parser failure | Non-fatal — document passes through unmodified | Warning log |
