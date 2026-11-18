'use client';

import { useState } from 'react';
import { X } from 'lucide-react';
import { ApiError, fileReport, type ApiReportReason } from '@/lib/api';

const REASONS: { value: ApiReportReason; label: string }[] = [
  { value: 'spam', label: 'Spam or misleading' },
  { value: 'counterfeit', label: 'Selling fake goods' },
  { value: 'inappropriate', label: 'Inappropriate content' },
  { value: 'harassment', label: 'Harassment or bullying' },
  { value: 'other', label: 'Something else' },
];

// "Report this video" for a live, whether it is on air now or a recording. The reasons are the same everywhere in the app.
export function LiveReportDialog({ streamId, onClose }: { streamId: string; onClose: () => void }) {
  const [reason, setReason] = useState<ApiReportReason | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const send = async () => {
    if (!reason) return;
    setBusy(true);
    try {
      await fileReport({ target_type: 'live_stream', target_id: streamId, reason });
      setSent(true);
    } catch (e) {
      setNote(
        e instanceof ApiError && e.status === 401
          ? 'Log in to report a video.'
          : e instanceof ApiError
            ? e.message
            : "Couldn't send this report. Try again.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="theme-light fixed inset-0 z-[80] flex items-end justify-center bg-black/50 p-4 sm:items-center" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm rounded-2xl bg-surface p-5 text-text shadow-xl"
      >
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-[16px] font-extrabold">Report this video</h3>
          <button onClick={onClose} aria-label="Close" className="text-text-mute">
            <X size={18} />
          </button>
        </div>
        {sent ? (
          <>
            <p className="mt-3 text-[13.5px] text-text-mute">Thanks. We will take a look.</p>
            <button onClick={onClose} className="brand-gradient mt-4 w-full rounded-full py-2.5 text-[13.5px] font-bold text-white">
              Done
            </button>
          </>
        ) : (
          <>
            <div className="mt-3 flex flex-col gap-1.5">
              {REASONS.map((r) => (
                <button
                  key={r.value}
                  onClick={() => setReason(r.value)}
                  className={`rounded-xl px-3.5 py-2.5 text-left text-[13.5px] font-semibold ${
                    reason === r.value ? 'bg-accent/15 ring-2 ring-accent' : 'bg-box'
                  }`}
                >
                  {r.label}
                </button>
              ))}
            </div>
            {note && <p className="mt-2 text-[13px] font-semibold text-red-600">{note}</p>}
            <button
              onClick={() => void send()}
              disabled={!reason || busy}
              className="brand-gradient mt-4 w-full rounded-full py-2.5 text-[13.5px] font-bold text-white disabled:opacity-50"
            >
              {busy ? 'Sending…' : 'Send report'}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
