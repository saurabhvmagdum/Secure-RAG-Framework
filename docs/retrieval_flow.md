# Hybrid Retrieval & Reranking Flow

## Overview

The ISRO RAG Framework utilizes a triad of distinct retrieval pipelines: **Lexical (Keyword)**, **Semantic (Vector)**, and **Graph (Entity-Relationship)**. At query execution, requests are asynchronously fired into each of these isolated systems to pull varying types of evidence, mitigating the blindspots of any single approach. 

This flow strictly enforces `Authorization` and `Classification` guidelines. Under no circumstance does a query execute against boundaries that contradict the provided principal constraints.

---

## Architecture Flow

```
                      ┌───────────────────────────────────────────────┐
                      │            Hybrid Retrieval Service           │
                      │                                               │
 User Query ────────► │  1. QueryNormalizer                           │
                      │     └─ Lowercase, unicode, strip              │
                      │                                               │
                      │  2. Fan-out execution (Graceful Decay on fail)│
                      │     ├─ OpenSearchKeywordRetriever (BM25)      │
                      │     ├─ QdrantSemanticRetriever (Vectors)      │
                      │     └─ Neo4jGraphRetriever (Cypher Paths)     │
                      │                                               │
                      │  3. RecipRankFusion (EvidenceFusion)          │
                      │     ├─ [CHECKPOINT: pre_hybrid_merge]         │
                      │     └─ Dedupes doc/chunks & Sums 1/(k+rank)   │
                      │                                               │
                      │  4. ExplainableCrossEncoderReranker           │
                      │     ├─ Scores remaining chunk pool            │
                      │     └─ Drops candidates via MMR filtering     │
                      │                                               │
                      │  5. ConsolidatedEvidenceSet Generation        │
                      │     └─ Emits [RETRIEVAL_COMPLETE] Audit log   │
                      └───────────────────────────────────────────────┘
                                           │
                                           ▼
                             (To Verification / QA Agent)
```

## The Tri-Index Structure

| Index Type | Underlying Tech | Strengths | Constraints in Phase 3 |
|------------|-----------------|-----------|------------------------|
| **Keyword** | OpenSearch (`retrieve/keyword.py`) | Exact text mapping, acronym tracking, deterministic matches. | Bound by Elastic `bool` filters on domains. SECRET is physically omitted from OS. |
| **Semantic** | Qdrant (`retrieve/semantic.py`) | Conceptual grouping, varying taxonomy interpretation, intent alignment. | Applies `MatchAny` conditions per Sensitivity scale natively in vector search payload. |
| **Graph** | Neo4j (`retrieve/graph.py`) | Neighborhood expansion, discovering "A relates to B through C" logic. | Bound entirely by `WHERE node.sensitivity_level IN [allowed]` Cypher clauses. |

---

## Fail-Closed But Gracefully-Degraded

If Qdrant goes offline but OpenSearch is standing, the framework **will NOT crash the user request**. 

The `HybridRetrievalService` utilizes a simple try/except pattern bounding the `RetrievalError` exceptions thrown by the index Adapters (which themselves use generic `CircuitBreakers`).
If an adapter fails, it is simply bypassed locally (producing `0` chunks for its stream), the system logs the degradation, and fuses the remaining streams.

If ALL three indices fail, it emits an empty evidence block securely. The verification downstream handles 0-evidence queries correctly by answering "I do not have the information."

## Reciprocal Rank Fusion (RRF)

We can't sum Cosine score natively with BM25 score. Instead we take the ranked position from each individual list and aggregate them generically.

Formula per chunk:
`Unified Score = 1.0 / (60 + Lexical Rank) + 1.0 / (60 + Semantic Rank) + 1.0 / (60 + Graph Rank)`

Chunks with the same `doc_id:chunk_id` are natively merged and deduplicated. The `ConsolidatedEvidenceSet` records which unique indices actively surfaced the chunk.

## Explainable Reranking

Reranking passes pairs of `(Query, Filtered Chunk)` to a hugging-face style Cross Encoder model.

- **Explainability**: New scores are bound transparently to `chunk.score`.
- **MMR**: Maximal Marginal Relevance applies `diversity_lambda`. If 5 chunks express the exact same paragraph slightly shifted, MMR drops redundant duplicates, keeping evidence rich. (Stubbed mathematically in Phase 3 skeleton).
