import React, { useState } from 'react';

interface Props {
  onSearch: (query: string) => void;
  isLoading: boolean;
}

export default function QueryBar({ onSearch, isLoading }: Props) {
  const [val, setVal] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (val.trim()) {
      onSearch(val.trim());
    }
  };

  return (
    <div className="panel" style={{ padding: '1rem' }}>
      <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '1rem' }}>
        <input 
          type="text" 
          value={val} 
          onChange={(e) => setVal(e.target.value)} 
          placeholder="Ask the secure knowledge base..." 
          disabled={isLoading}
        />
        <button type="submit" disabled={isLoading || !val.trim()}>
          {isLoading ? 'Querying...' : 'Search'}
        </button>
      </form>
    </div>
  );
}
