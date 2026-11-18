'use client';

import { useEffect } from 'react';
import { reportError } from '@/lib/errorReport';

// The last safety net: used when even the page frame (layout) crashes. It replaces the whole page, so it brings its own <html>
// and plain inline styles (the app's stylesheet may not have loaded).
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => reportError('render', error), [error]);
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: 'system-ui, sans-serif' }}>
        <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, padding: 24, textAlign: 'center' }}>
          <p style={{ fontSize: 16, fontWeight: 800, margin: 0 }}>Something went wrong</p>
          <p style={{ fontSize: 13.5, margin: 0, maxWidth: 300, opacity: 0.7 }}>It has been reported. Reload the page to continue.</p>
          <button type="button" onClick={reset} style={{ padding: '10px 20px', borderRadius: 999, border: '1px solid #ccc', background: 'transparent', fontWeight: 700 }}>
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
