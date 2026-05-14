"use client";

import React, { useState } from 'react';
import QueryBar from './components/QueryBar';
import AnswerView from "./components/AnswerView";
import FallbackView from './components/FallbackView';
import EvidenceDrawer from './components/EvidenceDrawer';
import { executeQuery } from '../lib/api';
import { QueryResponse } from '../lib/types';

export default function Page() {
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleQuery = async (query: string) => {
    setLoading(true);
    setError(null);
    setResponse(null);
    
    try {
      const res = await executeQuery({ query });
      setResponse(res);
    } catch (_err: unknown) {
      setError("Secure gateway rejection or internal error occurred.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      
      <QueryBar onSearch={handleQuery} isLoading={loading} />

      {error && (
        <div className="panel badge-blocked" style={{ textAlign: 'center', backgroundColor: 'var(--status-blocked-bg)' }}>
          {error}
        </div>
      )}

      {response && response.route === "HIGH_CONFIDENCE" && (
        <AnswerView response={response} />
      )}

      {response && response.route === "FALLBACK_PARTIAL" && (
        <FallbackView response={response} />
      )}

      {response && response.route === "BLOCKED" && (
        <div className="panel" style={{ border: '1px solid var(--status-blocked-text)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem' }}>
            <h2>Operation Blocked</h2>
            <span className="badge badge-blocked">BLOCKED</span>
          </div>
          <p style={{ color: 'var(--text-muted)' }}>{response.blocking_explanation}</p>
          <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
            {response.reason_codes.map(code => (
              <span key={code} className="badge badge-blocked" style={{ opacity: 0.8 }}>{code}</span>
            ))}
          </div>
        </div>
      )}

      {response && <EvidenceDrawer snippets={response.evidence_snippets} />}

    </div>
  );
}
