import React from 'react';
import { SafeSnippet } from '../../lib/types';

export default function EvidenceDrawer({ snippets }: { snippets: SafeSnippet[] }) {
  
  if (!snippets || snippets.length === 0) return null;

  return (
    <div style={{ marginTop: '2rem' }}>
      <h3 style={{ borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem', marginBottom: '1rem' }}>
        Source Provenance
      </h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {snippets.map((snip) => (
           <div key={snip.chunk_id} style={{ padding: '1rem', backgroundColor: 'var(--bg-color)', border: '1px solid var(--border-color)', borderRadius: '4px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--accent-blue)', marginBottom: '0.5rem' }}>
                 <span style={{ fontWeight: 600 }}>[{snip.chunk_id}]</span>
                 <span>{snip.section_path}</span>
              </div>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                 {snip.text}
              </div>
           </div>
        ))}
      </div>
    </div>
  );
}
