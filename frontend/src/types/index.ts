/**
 * ISRO RAG Framework — Shared TypeScript Types
 * ==============================================
 *
 * TypeScript interfaces mirroring backend Pydantic models.
 * Used by frontend components for type-safe API interaction.
 *
 * IMPORTANT: These types must stay in sync with backend models.
 * Only approved metadata fields are included.
 */

// ── Metadata ────────────────────────────────────────────────────────────────

export type DomainTag =
  | 'propulsion'
  | 'avionics'
  | 'structures'
  | 'thermal'
  | 'navigation'
  | 'telemetry'
  | 'procurement'
  | 'administration'
  | 'failure_analysis'
  | 'quality_assurance'
  | 'mission_planning'
  | 'ground_systems'
  | 'launch_operations'
  | 'human_resources'
  | 'general';

export type SensitivityLevel = 'PUBLIC' | 'INTERNAL' | 'CONFIDENTIAL' | 'SECRET';

export interface DocumentMetadata {
  domain_tag: DomainTag;
  sensitivity_level: SensitivityLevel;
  version: string;
  origin: string;
}

// ── Evidence ────────────────────────────────────────────────────────────────

export type IndexType = 'keyword' | 'semantic' | 'graph';

export interface EvidenceChunk {
  doc_id: string;
  chunk_id: string;
  text: string;
  rank: number;
  index_type: IndexType;
  score: number;
  section_path: string;
  metadata: DocumentMetadata;
}

// ── Answer ──────────────────────────────────────────────────────────────────

export type RoutingRoute = 'HIGH_CONFIDENCE' | 'FALLBACK_PARTIAL' | 'BLOCKED';

export interface VerificationResult {
  relevance: number;
  coverage: number;
  similarity: number;
  consistency: number;
  domain_rules: number;
  issues: string[];
  iterations: number;
}

export interface RoutingDecision {
  route: RoutingRoute;
  confidence: number;
  threshold_applied: number;
  explanation: string;
}

export interface VerifiedAnswer {
  query_id: string;
  answer_text: string;
  cited_chunks: string[];
  verification: VerificationResult;
  routing: RoutingDecision;
  evidence_snippets: Array<{
    chunk_id: string;
    text: string;
    doc_id: string;
    section_path: string;
  }>;
  timestamp: string;
}

// ── API Request/Response ────────────────────────────────────────────────────

export interface QueryRequest {
  query: string;
  domain_filter?: string[] | null;
  max_sensitivity?: string | null;
}

export interface QueryResponse {
  query_id: string;
  query: string;
  answer_text: string;
  confidence: number;
  confidence_label: RoutingRoute;
  cited_sources: Array<Record<string, string>>;
  evidence_snippets: Array<Record<string, string>>;
  verification_summary: Record<string, number>;
  timestamp: string;
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export type PrincipalType = 'USER' | 'SERVICE';

export interface Principal {
  principal_id: string;
  type: PrincipalType;
  display_name: string;
  roles: string[];
}

// ── Health ───────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  version: string;
  timestamp: string;
  services: Record<string, string>;
}

export interface ReadinessResponse {
  ready: boolean;
  checks: Record<string, boolean>;
}
