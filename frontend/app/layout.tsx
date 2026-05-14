import './globals.css';
import React from 'react';

export const metadata = {
  title: 'ISRO Operations | Secure RAG',
  description: 'Enterprise internal knowledge retrieval hub',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <header style={{ borderBottom: '1px solid var(--border-color)', padding: '1rem 2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span style={{ fontWeight: 800, color: 'var(--accent-orange)', marginRight: '8px' }}>ISRO</span>
            <span style={{ color: 'var(--text-muted)' }}>Secure Operations RAG</span>
          </div>
          <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Internal Network Only</div>
        </header>
        <main className="container">
          {children}
        </main>
      </body>
    </html>
  );
}
