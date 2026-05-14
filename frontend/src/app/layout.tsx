import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'ISRO RAG — Secure Knowledge Base',
  description:
    'Secure, on-premise Retrieval-Augmented Generation platform for ISRO internal knowledge bases. Grounded, verifiable, source-linked answers.',
  robots: 'noindex, nofollow', // Internal-only — never index
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        {/* Top navigation bar */}
        <header
          style={{
            position: 'sticky',
            top: 0,
            zIndex: 50,
            borderBottom: '1px solid var(--color-border)',
            background: 'var(--glass-bg)',
            backdropFilter: 'blur(12px)',
            WebkitBackdropFilter: 'blur(12px)',
          }}
        >
          <div
            className="container flex-between"
            style={{ height: '64px' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              {/* ISRO Logo placeholder — replace with actual asset */}
              <div
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, var(--color-primary), var(--color-accent))',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 700,
                  fontSize: '0.75rem',
                  color: 'white',
                }}
              >
                RAG
              </div>
              <div>
                <div style={{ fontSize: '0.9375rem', fontWeight: 600, lineHeight: 1.2 }}>
                  ISRO RAG Framework
                </div>
                <div
                  style={{
                    fontSize: '0.6875rem',
                    color: 'var(--color-text-muted)',
                    letterSpacing: '0.05em',
                    textTransform: 'uppercase',
                  }}
                >
                  Secure • On-Premise • Verified
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              <div
                className="badge badge-high"
                style={{ fontSize: '0.625rem' }}
              >
                ● Air-Gapped
              </div>
              {/* TODO: Phase 4 — Auth-aware user menu */}
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: '50%',
                  background: 'var(--color-bg-tertiary)',
                  border: '1px solid var(--color-border)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '0.75rem',
                  color: 'var(--color-text-secondary)',
                }}
              >
                U
              </div>
            </div>
          </div>
        </header>

        <main>{children}</main>
      </body>
    </html>
  );
}
