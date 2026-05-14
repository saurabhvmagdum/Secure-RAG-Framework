export type RoutingRoute = "HIGH_CONFIDENCE" | "FALLBACK_PARTIAL" | "BLOCKED";

export interface SafeSnippet {
    chunk_id: string;
    doc_id: string;
    text: string;
    section_path: string;
}

export interface MetricBreakdown {
    relevance: number;
    intent_coverage: number;
    claim_similarity: number;
    consistency: number;
    citation_integrity: number;
    domain_rules: number;
}

export interface QueryResponse {
    request_id: string;
    correlation_id: string;
    route: RoutingRoute;
    confidence_score: number;
    reason_codes: string[];
    metric_breakdown: MetricBreakdown;
    
    answer_text: string | null;
    evidence_snippets: SafeSnippet[];
    citations: string[];
    
    fallback_explanation: string | null;
    blocking_explanation: string | null;
}

export interface QueryRequest {
    query: string;
    domain_tags?: string[];
    max_sensitivity?: string;
}
