'use client';

import { useEffect, useState } from 'react';
import { ApiError, getMyNoShowClaims, replyToNoShow, uploadFile, type ApiOpenNoShow } from '@/lib/api';

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : '');

// Seller: buyers who say they went to the pickup address and found nobody there. The buyer was refunded; you have 48 hours to answer
// with a note and a photo from your pickup address, and our team decides. A strike is added only if they agree with the buyer.
export function NoShowReplies() {
  const [claims, setClaims] = useState<ApiOpenNoShow[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [photo, setPhoto] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    getMyNoShowClaims().then(setClaims).catch(() => {});
  };
  useEffect(load, []);

  if (claims.length === 0) return null;

  const send = (orderId: string) => {
    setBusy(true);
    setError(null);
    (async () => {
      const url = photo ? (await uploadFile(photo)).url : undefined;
      await replyToNoShow(orderId, note.trim(), url);
    })()
      .then(() => {
        setOpen(null);
        setNote('');
        setPhoto(null);
        load();
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not send. Try again.'))
      .finally(() => setBusy(false));
  };

  return (
    <div className="mb-4 rounded-xl border border-line bg-surface p-3.5 text-[12.5px] leading-snug text-text">
      <p className="text-[13.5px] font-bold">A buyer has reported a problem at your pickup address</p>
      {claims.map((c) => (
        <div key={c.order_id} className="mt-2 border-t border-line pt-2">
          <p className="font-bold">{c.product_name ?? 'Order'}</p>
          <p className="text-text-mute">
            {c.kind === 'refused' ? 'They say you were there but would not show or sell it to them. ' : 'They say nobody was there. '}
            {c.planned_for ? `They planned to come ${when(c.planned_for)}. ` : ''}They were refunded.
            {c.buyer_note ? ` They wrote: ${c.buyer_note}` : ''}
          </p>
          {c.replied ? (
            <p className="mt-1 text-text-mute">You replied. Our team will decide.</p>
          ) : open === c.order_id ? (
            <div className="mt-1.5">
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                maxLength={500}
                placeholder="What happened? Were you there?"
                className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-base text-text focus:border-mark focus:outline-none sm:text-[13px]"
              />
              <label className="mt-1.5 block text-text-mute">
                A photo taken now at your pickup address (optional, but it helps):
                <input type="file" accept="image/*" capture="environment" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} className="mt-1 block w-full text-[12px]" />
              </label>
              <div className="mt-1.5 flex gap-2">
                <button onClick={() => send(c.order_id)} disabled={busy || note.trim().length < 3} className="rounded-full btn-neutral px-3 py-1.5 font-bold disabled:opacity-50">
                  {busy ? 'Sending…' : 'Send reply'}
                </button>
                <button onClick={() => setOpen(null)} className="rounded-full border border-line px-3 py-1.5 font-bold text-text-mute">
                  Cancel
                </button>
              </div>
              {error && <p className="mt-1 text-red-600">{error}</p>}
            </div>
          ) : (
            <button onClick={() => setOpen(c.order_id)} className="mt-1 font-bold underline">
              Reply by {when(c.reply_by)}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
