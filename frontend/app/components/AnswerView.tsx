import React from 'react';
import { QueryResponse } from '../../lib/types';

export default function AnswerView({ response }: { response: QueryResponse }) {
  
  // Format citations automatically replacing [doc_id:chunk_id] with styled tags
  const renderFormattedText = (text: string) => {
    // We split by standard chunk citation tags natively inserted by the LLM 
    const regex = /\[([^:]+):([^\]]+)\]/g;
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(text.substring(lastIndex, match.index));
      }
      parts.push(
        <cite key={match.index} title={`Source: ${match[1]}`}>
          {match[2]}
        </cite>
      );
      lastIndex = regexpLastIndex(regex);
    }
    if (lastIndex < text.length) {
      parts.push(text.substring(lastIndex));
    }

    return parts;
  };

  function regexpLastIndex(regex: RegExp) {
      return regex.lastIndex;
  }

  return (
    <div className="panel" style={{ borderLeft: '4px solid var(--status-high-text)' }}>
      
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
        <div>
          <span className="badge badge-high" style={{ marginRight: '1rem' }}>VERIFIED RESPONSE</span>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>ID: {response.correlation_id}</span>
        </div>
        <div style={{ fontWeight: 600, color: 'var(--status-high-text)' }}>
          Confidence: {(response.confidence_score * 100).toFixed(1)}%
        </div>
      </div>

      <p style={{ fontSize: '1.1rem', lineHeight: '1.6', marginBottom: '1.5rem', whiteSpace: 'pre-wrap' }}>
        {renderFormattedText(response.answer_text || "")}
      </p>

      <div style={{ backgroundColor: '#0a0d14', padding: '1rem', borderRadius: '4px', fontSize: '0.85rem' }}>
         <h4 style={{ color: 'var(--text-muted)', marginBottom: '0.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.2rem' }}>Metric Breakdown</h4>
         <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem', color: '#d1d5db' }}>
            <div>Relevance: {(response.metric_breakdown.relevance * 100).toFixed(0)}%</div>
            <div>Similarity: {(response.metric_breakdown.claim_similarity * 100).toFixed(0)}%</div>
            <div>Consistency: {(response.metric_breakdown.consistency * 100).toFixed(0)}%</div>
         </div>
      </div>

    </div>
  );
}
