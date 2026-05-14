import React from 'react';
import { QueryResponse } from '../../lib/types';

export default function FallbackView({ response }: { response: QueryResponse }) {
  
  return (
    <div className="panel" style={{ borderLeft: '4px solid var(--status-warn-text)' }}>
      
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
        <div>
          <span className="badge badge-warn" style={{ marginRight: '1rem' }}>PARTIAL EVIDENCE / UNVERIFIED</span>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>ID: {response.correlation_id}</span>
        </div>
        <div style={{ fontWeight: 600, color: 'var(--status-warn-text)' }}>
          Confidence Limit Reached: {(response.confidence_score * 100).toFixed(1)}%
        </div>
      </div>

      <div style={{ backgroundColor: 'var(--status-warn-bg)', padding: '1rem', border: '1px solid var(--border-color)', borderRadius: '4px', marginBottom: '1.5rem', color: 'var(--text-main)', fontSize: '0.9rem' }}>
        <strong>Explanation: </strong> {response.fallback_explanation}
        <div style={{ marginTop: '0.5rem' }}>
            {response.reason_codes.map(r => (
                <span key={r} className="badge badge-warn" style={{ marginRight: '0.5rem', opacity: 0.8 }}>{r}</span>
            ))}
        </div>
      </div>

      <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>The system suppressed the synthesized answer due to policy thresholds. Extracted snippets are provided below.</p>

      {/* Exposing snippets natively */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {response.evidence_snippets.map((snip) => (
           <div key={snip.chunk_id} style={{ padding: '1rem', backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '4px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--accent-blue)', marginBottom: '0.5rem' }}>
                 <span>DOC: {snip.doc_id}</span>
                 <span>PATH: {snip.section_path}</span>
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.9rem' }}>
                 {snip.text}
              </div>
           </div>
        ))}
      </div>

    </div>
  );
}
