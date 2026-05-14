'use client';

import { useState } from 'react';

export default function HomePage() {
  const [query, setQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsLoading(true);
    // TODO: Phase 4 — integrate with /api/v1/query endpoint
    setTimeout(() => setIsLoading(false), 1000);
  };

  return (
    <div className="container" style={{ paddingTop: 'var(--space-3xl)' }}>
      {/* Hero Section */}
      <div
        className="animate-fade-in"
        style={{ textAlign: 'center', marginBottom: 'var(--space-3xl)' }}
      >
        <h1
          style={{
            fontSize: '2.5rem',
            fontWeight: 700,
            marginBottom: 'var(--space-md)',
            background: 'linear-gradient(135deg, var(--color-primary-light), var(--color-accent))',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}
        >
          Mission Knowledge Base
        </h1>
        <p
          style={{
            maxWidth: '600px',
            margin: '0 auto',
            fontSize: '1.0625rem',
            color: 'var(--color-text-secondary)',
          }}
        >
          Ask questions about technical manuals, failure analysis reports,
          procurement rules, and operational procedures. Every answer is
          grounded in verified evidence.
        </p>
      </div>

      {/* Query Input */}
      <div
        className="glass-card animate-fade-in"
        style={{
          maxWidth: '800px',
          margin: '0 auto var(--space-2xl)',
          padding: 'var(--space-lg)',
        }}
      >
        <form onSubmit={handleSubmit}>
          <div style={{ display: 'flex', gap: 'var(--space-sm)' }}>
            <input
              id="query-input"
              className="input"
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Enter your query — e.g., 'What were the root causes of anomaly X?'"
              style={{ flex: 1, padding: '12px 16px' }}
              disabled={isLoading}
            />
            <button
              id="submit-query"
              className="btn btn-primary"
              type="submit"
              disabled={isLoading || !query.trim()}
              style={{ padding: '12px 24px', whiteSpace: 'nowrap' }}
            >
              {isLoading ? 'Searching...' : 'Search'}
            </button>
          </div>
        </form>
      </div>

      {/* Status Cards */}
      <div
        className="animate-fade-in"
        style={{
          maxWidth: '800px',
          margin: '0 auto',
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 'var(--space-md)',
        }}
      >
        {/* Tri-Index Status */}
        <div className="glass-card" style={{ padding: 'var(--space-md)' }}>
          <div
            style={{
              fontSize: '0.75rem',
              color: 'var(--color-text-muted)',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              marginBottom: 'var(--space-sm)',
            }}
          >
            Retrieval Indices
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div className="flex-between">
              <span style={{ fontSize: '0.8125rem', color: 'var(--color-text-secondary)' }}>
                BM25 (OpenSearch)
              </span>
              <span className="badge badge-partial" style={{ fontSize: '0.625rem' }}>
                Phase 2
              </span>
            </div>
            <div className="flex-between">
              <span style={{ fontSize: '0.8125rem', color: 'var(--color-text-secondary)' }}>
                Semantic (Qdrant)
              </span>
              <span className="badge badge-partial" style={{ fontSize: '0.625rem' }}>
                Phase 2
              </span>
            </div>
            <div className="flex-between">
              <span style={{ fontSize: '0.8125rem', color: 'var(--color-text-secondary)' }}>
                Graph (Neo4j)
              </span>
              <span className="badge badge-partial" style={{ fontSize: '0.625rem' }}>
                Phase 2
              </span>
            </div>
          </div>
        </div>

        {/* Security Status */}
        <div className="glass-card" style={{ padding: 'var(--space-md)' }}>
          <div
            style={{
              fontSize: '0.75rem',
              color: 'var(--color-text-muted)',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              marginBottom: 'var(--space-sm)',
            }}
          >
            Security & Governance
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div className="flex-between">
              <span style={{ fontSize: '0.8125rem', color: 'var(--color-text-secondary)' }}>
                RBAC Engine
              </span>
              <span className="badge badge-high" style={{ fontSize: '0.625rem' }}>
                Active
              </span>
            </div>
            <div className="flex-between">
              <span style={{ fontSize: '0.8125rem', color: 'var(--color-text-secondary)' }}>
                Audit Logging
              </span>
              <span className="badge badge-high" style={{ fontSize: '0.625rem' }}>
                Active
              </span>
            </div>
            <div className="flex-between">
              <span style={{ fontSize: '0.8125rem', color: 'var(--color-text-secondary)' }}>
                Encryption (AES-256)
              </span>
              <span className="badge badge-high" style={{ fontSize: '0.625rem' }}>
                Active
              </span>
            </div>
          </div>
        </div>

        {/* Verification Status */}
        <div className="glass-card" style={{ padding: 'var(--space-md)' }}>
          <div
            style={{
              fontSize: '0.75rem',
              color: 'var(--color-text-muted)',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              marginBottom: 'var(--space-sm)',
            }}
          >
            Verification Pipeline
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div className="flex-between">
              <span style={{ fontSize: '0.8125rem', color: 'var(--color-text-secondary)' }}>
                Confidence Scoring
              </span>
              <span className="badge badge-high" style={{ fontSize: '0.625rem' }}>
                Ready
              </span>
            </div>
            <div className="flex-between">
              <span style={{ fontSize: '0.8125rem', color: 'var(--color-text-secondary)' }}>
                Threshold Routing
              </span>
              <span className="badge badge-high" style={{ fontSize: '0.625rem' }}>
                Ready
              </span>
            </div>
            <div className="flex-between">
              <span style={{ fontSize: '0.8125rem', color: 'var(--color-text-secondary)' }}>
                Grounding Loop
              </span>
              <span className="badge badge-partial" style={{ fontSize: '0.625rem' }}>
                Phase 3
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
