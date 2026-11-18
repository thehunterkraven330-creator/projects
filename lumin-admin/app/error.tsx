'use client';

import { useEffect } from 'react';
import { reportError } from '@/lib/errorReport';

// Shown instead of a blank screen when a screen crashes while drawing. The crash is reported (see lib/errorReport.ts).
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => reportError('render', error), [error]);
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 p-6 text-center">
      <p className="text-[16px] font-extrabold text-text">Something went wrong</p>
      <p className="max-w-[300px] text-[13.5px] text-text-mute">This screen hit a problem. It has been reported. Try again, and if it keeps happening, reload the page.</p>
      <button type="button" onClick={reset} className="rounded-full border border-line px-5 py-2.5 text-[13.5px] font-bold text-text">
        Try again
      </button>
    </div>
  );
}
