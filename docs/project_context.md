Problem statement
Provide secure, hallucination-free, highly verifiable answers from mission-critical ISRO documents using fully on-premise GPUs and storage only.

Ensure every answer is grounded in retrieved evidence, explicitly linked to document fragments, and accompanied by a computed confidence score suitable for operational decision-making.

Maintain strict isolation from external networks while enforcing RBAC, data classification, encryption, and full auditability across the entire RAG pipeline.

High-level system architecture
Layer 1 – Data & Knowledge: Central ingestion and curation layer that normalizes heterogeneous documents, performs chunking, applies governed metadata tagging, and persists content into three coordinated indices (lexical, semantic, and knowledge graph).

Layer 2 – Hybrid Retrieval & Reranking: Query-time pipeline that executes BM25 keyword search, semantic vector search, and graph-based reasoning in parallel, then consolidates and reranks results into a single evidence set for downstream consumption.

Layer 3 – Verification & Grounding: Deterministic loop that generates a draft answer from the Consolidated Evidence Set, validates it against relevance/coverage/similarity/consistency metrics and domain rules, and computes a confidence score before routing.

Layer 4 – Generation & Interaction: Domain-adapted LLM layer that produces user-facing responses with explicit source citations and confidence labels, exposed via a secure internal React/Next.js interface and bound to the security and governance layer.

Data sources
Q&A Docs: Curated question–answer collections for common operational, technical, and administrative topics.

Failure Analysis Reports: Post-incident and anomaly investigation documents containing timelines, root-cause analyses, and corrective actions.

Technical Manuals: System, subsystem, and component manuals, interface control documents, and operational procedures.

Machine Telemetry Stories: Structured and semi-structured narratives derived from telemetry feeds, logs, and monitoring summaries.

Procurement Rules: Policies, reference templates, eligibility rules, and compliance constraints for procurement workflows.

Admin Notes: Internal memoranda, meeting minutes, circulars, and administrative guidelines relevant to day-to-day operations.

