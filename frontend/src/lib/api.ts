/**
 * ISRO RAG Framework — Internal API Client
 * ==========================================
 *
 * HTTP client for communicating with the backend API.
 * ONLY connects to internal/localhost — zero external URLs.
 *
 * All requests include:
 * - Authorization: Bearer <token>
 * - X-Correlation-ID for tracing
 * - Content-Type: application/json
 */

import type {
  HealthResponse,
  QueryRequest,
  QueryResponse,
  ReadinessResponse,
} from '@/types';

// ── Configuration ───────────────────────────────────────────────────────────

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1';

// ── Helpers ─────────────────────────────────────────────────────────────────

function generateCorrelationId(): string {
  return crypto.randomUUID();
}

function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('isro_rag_token');
}

async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getAuthToken();
  const correlationId = generateCorrelationId();

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Correlation-ID': correlationId,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string> || {}),
  };

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({
      detail: response.statusText,
    }));
    throw new ApiError(
      response.status,
      error.detail || 'Request failed',
      correlationId
    );
  }

  return response.json() as Promise<T>;
}

// ── Error ───────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    public readonly correlationId: string
  ) {
    super(`API Error ${status}: ${detail}`);
    this.name = 'ApiError';
  }
}

// ── API Methods ─────────────────────────────────────────────────────────────

/** Submit a RAG query */
export async function submitQuery(
  request: QueryRequest
): Promise<QueryResponse> {
  return apiRequest<QueryResponse>('/query', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/** Health check */
export async function getHealth(): Promise<HealthResponse> {
  return apiRequest<HealthResponse>('/health');
}

/** Readiness check */
export async function getReadiness(): Promise<ReadinessResponse> {
  return apiRequest<ReadinessResponse>('/ready');
}

/** Query audit logs (admin) */
export async function getAuditLogs(params?: {
  principal_id?: string;
  action?: string;
  correlation_id?: string;
  limit?: number;
}): Promise<{ total: number; events: Record<string, unknown>[] }> {
  const searchParams = new URLSearchParams();
  if (params?.principal_id) searchParams.set('principal_id', params.principal_id);
  if (params?.action) searchParams.set('action', params.action);
  if (params?.correlation_id)
    searchParams.set('correlation_id', params.correlation_id);
  if (params?.limit) searchParams.set('limit', String(params.limit));

  const query = searchParams.toString();
  return apiRequest(`/admin/audit${query ? `?${query}` : ''}`);
}
