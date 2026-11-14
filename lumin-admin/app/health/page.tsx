'use client';

import { useState } from 'react';
import { AdminShell } from '@/components/AdminShell';
import { ApiError, checkCounters, fixCounters, type ApiCounterReport } from '@/lib/api';

const LABELS: Record<string, string> = { video_posts: 'Videos', comments: 'Comments', products: 'Products' };
const COLUMNS: Record<string, string> = {
  likes_count: 'likes',
  comments_count: 'comments',
  shares_count: 'shares',
  saves_count: 'saves',
  views_count: 'views',
  unique_viewers_count: 'unique viewers',
  cart_count: 'bought & in carts',
};

export default function NumberCheckPage() {
  const [report, setReport] = useState<ApiCounterReport | null>(null);
  const [wrong, setWrong] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [fixed, setFixed] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = (fix: boolean) => {
    setBusy(true);
    setError(null);
    setFixed(null);
    (fix ? fixCounters() : checkCounters())
      .then((r) => {
        setReport(r.details);
        if ('corrected_total' in r) {
          setFixed(r.corrected_total);
          setWrong(0);
        } else setWrong(r.wrong_total);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'That failed.'))
      .finally(() => setBusy(false));
  };

  return (
    <AdminShell>
      <p className="mb-1 text-[20px] font-bold text-text">Number check</p>
      <p className="mb-5 max-w-2xl text-[13px] text-text-mute">
        Recounts every like, comment, share, save, view and &ldquo;bought &amp; in carts&rdquo; number from the real records behind it, and shows
        where a stored number is different. Checking changes nothing. Fixing sets each wrong number to the recount, so demo
        videos with made-up numbers (for example 520 likes with nobody having liked them) would drop to the real figure.
      </p>
      {error && <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>}
      <div className="mb-5 flex gap-2">
        <button disabled={busy} onClick={() => run(false)} className="rounded-lg bg-text px-4 py-2 text-[13px] font-bold text-white disabled:opacity-60">
          {busy ? 'Working…' : 'Check the numbers'}
        </button>
        {wrong !== null && wrong > 0 && fixed === null && (
          <button disabled={busy} onClick={() => run(true)} className="rounded-lg border border-line bg-white px-4 py-2 text-[13px] font-bold text-text disabled:opacity-60">
            Fix {wrong} wrong number{wrong === 1 ? '' : 's'}
          </button>
        )}
      </div>
      {fixed !== null && <p className="mb-4 rounded-lg bg-green-50 px-3 py-2 text-[13px] text-green-800">Fixed {fixed} number{fixed === 1 ? '' : 's'}.</p>}
      {report && wrong === 0 && fixed === null && <p className="rounded-lg bg-green-50 px-3 py-2 text-[13px] text-green-800">Every number matches its records.</p>}
      {report &&
        (wrong ?? 0) > 0 &&
        Object.entries(report).map(([table, cols]) =>
          Object.entries(cols)
            .filter(([, c]) => c.wrong > 0)
            .map(([col, c]) => (
              <div key={`${table}.${col}`} className="mb-3 rounded-xl border border-line bg-white p-4">
                <p className="text-[13.5px] font-bold text-text">
                  {LABELS[table] ?? table}: {c.wrong} with wrong {COLUMNS[col] ?? col}
                </p>
                <ul className="mt-2 space-y-0.5 text-[12px] text-text-mute">
                  {c.examples.map(([id, stored, real]) => (
                    <li key={id}>
                      <span className="font-mono">{id.slice(0, 8)}</span>: shows {stored}, real count is {real}
                    </li>
                  ))}
                </ul>
              </div>
            )),
        )}
    </AdminShell>
  );
}
