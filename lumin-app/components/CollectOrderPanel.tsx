'use client';

import { useState } from 'react';
import { MapPin, ShieldCheck } from 'lucide-react';
import { ApiError, collectAccept, collectComing, collectReject, uploadFile, type CollectRejectCode } from '@/lib/api';
import type { Order } from '@/lib/types';

const errText = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

const fmt = (iso?: string) => (iso ? new Date(iso).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '');

// Seller side of a "collect in person" order: nothing to send. The buyer has paid (held) and comes to the shop's pickup address.
export function SellerCollectPanel({ order }: { order: Order }) {
  if (order.status === 'cancelled') return null;
  if (order.status === 'delivered') {
    return (
      <p className="mt-1.5 flex items-start gap-1.5 rounded-lg bg-panel px-2.5 py-1.5 text-[12.5px] text-text">
        <ShieldCheck size={14} className="mt-0.5 shrink-0 text-green-600" />
        The buyer inspected and accepted it. Hand it over now. Your payment is released.
      </p>
    );
  }
  if (order.status !== 'pending') return null;
  return (
    <div className="mt-1.5 rounded-lg bg-panel px-2.5 py-2 text-[12.5px] leading-snug text-text">
      <p className="flex items-center gap-1.5 font-bold">
        <MapPin size={14} className="shrink-0 text-text-mute" /> Collect in person · {order.buyerName} has paid (held safely)
      </p>
      <p className="mt-1 text-text-mute">
        They will come to your pickup address{order.collectDeadline ? ` before ${fmt(order.collectDeadline)}` : ''}
        {order.collectHours ? `, during your visiting hours (${order.collectHours})` : ''}. Be there.
      </p>
      {order.visitDetails && <p className="mt-1 font-bold">The buyer plans to come: {order.visitDetails}</p>}
      <p className="mt-1 text-text-mute">Hand the item over only when this order shows as delivered (the buyer accepted).</p>
      <p className="mt-1 text-text-mute">
        If you meet at home, keep the meeting somewhere open, don&apos;t be alone if you can help it, and never take cash or a transfer from
        the buyer: they have already paid. If nobody from your side is there during your visiting hours, the buyer is refunded and it counts
        against you.
      </p>
    </div>
  );
}

// Buyer side: where to go, when, the seller's phone; then Accept (the seller is paid) or Reject (full refund).
export function BuyerCollectPanel({ order, units = 1, onChanged }: { order: Order; units?: number; onChanged?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState('');
  const [code, setCode] = useState<CollectRejectCode>('not_as_described');
  const [photo, setPhoto] = useState<File | null>(null);
  const [when, setWhen] = useState('');
  const [error, setError] = useState<string | null>(null);

  if (order.status === 'cancelled') return null;
  if (order.status === 'delivered') {
    return (
      <p className="mt-3 flex items-center gap-1.5 text-[12.5px] text-green-600">
        <ShieldCheck size={16} /> You accepted this after inspecting it in person.
      </p>
    );
  }
  if (order.status !== 'pending') return null;

  const run = (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    fn()
      .then(() => {
        setConfirming(false);
        onChanged?.();
      })
      .catch((e) => setError(errText(e, 'Something went wrong. Try again.')))
      .finally(() => setBusy(false));
  };

  // "Nobody was there" counts only once the time the buyer told the seller has passed.
  const noShowOpen = !!order.visitDetailsAt && new Date(order.visitDetailsAt).getTime() < Date.now();
  const whenDate = when ? new Date(when) : null;
  const whenOk = !!whenDate && !Number.isNaN(whenDate.getTime()) && whenDate.getTime() > Date.now();

  return (
    <div className="mt-3 rounded-lg bg-panel px-3 py-2.5 text-[12.5px] leading-snug text-text">
      <p className="flex items-center gap-1.5 font-bold">
        <MapPin size={14} className="shrink-0 text-text-mute" /> Collect in person{units > 1 ? ` · ${units} units` : ''}
      </p>
      {units > 1 && <p className="mt-1 text-text-mute">These {units} units are collected together: Accept and Reject apply to all of them.</p>}
      <p className="mt-1">
        You have paid and the money is held safely. Go to:
        <br />
        <span className="font-bold">{order.collectAddress ?? 'The seller has not set an address yet. Contact support.'}</span>
      </p>
      {order.collectContactName && <p className="mt-1">Ask for: {order.collectContactName}</p>}
      {order.collectPhone && (
        <p className="mt-0.5">
          Phone: <a href={`tel:${order.collectPhone}`} className="font-bold underline">{order.collectPhone}</a>
        </p>
      )}
      {order.collectHours && <p className="mt-0.5">Visiting hours: {order.collectHours}</p>}
      {order.collectDeadline && <p className="mt-0.5">Come before: <span className="font-bold">{fmt(order.collectDeadline)}</span>, or the order is cancelled and refunded.</p>}

      <div className="mt-2 rounded-lg border border-line bg-surface p-2">
        {order.visitDetails ? (
          <p className="font-bold">You told the seller you are coming: {order.visitDetails}</p>
        ) : (
          <p className="text-text-mute">Tell the seller when you are coming so someone is there.</p>
        )}
        <div className="mt-1.5 flex gap-2">
          <input
            type="datetime-local"
            value={when}
            onChange={(e) => setWhen(e.target.value)}
            className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-base text-text focus:border-mark focus:outline-none sm:text-[13px]"
          />
          <button
            onClick={() => whenDate && run(() => collectComing(order.id, whenDate))}
            disabled={busy || !whenOk}
            className="shrink-0 rounded-full border border-line px-3 py-1.5 text-[12.5px] font-bold text-text disabled:opacity-50"
          >
            {order.visitDetails ? 'Change' : "I'm coming"}
          </button>
        </div>
      </div>

      <p className="mt-2 text-text-mute">
        Never pay anything at the visit, in cash or by transfer. Your payment is already held. Look the item over first. Tap Accept only when
        you are happy and the item is in front of you. If it isn&apos;t right, tap Reject and you are refunded in full.
      </p>
      <p className="mt-1.5 text-text-mute">
        Staying safe: go in daylight, tell someone where you are going, bring a friend if you can, and meet at the address shown here. If
        anything feels wrong, leave. You can always reject and be refunded.
      </p>
      {!rejecting && !confirming && (
        <div className="mt-2 flex flex-wrap gap-2">
          <button onClick={() => setConfirming(true)} disabled={busy} className="rounded-full btn-neutral px-3 py-1.5 text-[12.5px] font-bold disabled:opacity-50">
            Accept: it is what I ordered
          </button>
          <button onClick={() => setRejecting(true)} disabled={busy} className="rounded-full border border-line px-3 py-1.5 text-[12.5px] font-bold text-text-mute">
            Reject and refund
          </button>
        </div>
      )}
      {confirming && (
        <div className="mt-2 rounded-lg border border-line bg-surface p-2">
          <p className="font-bold">Are you at the seller with the item in front of you? Accepting pays the seller now and can&apos;t be undone.</p>
          <div className="mt-1.5 flex gap-2">
            <button onClick={() => run(() => collectAccept(order.id))} disabled={busy} className="rounded-full btn-neutral px-3 py-1.5 text-[12.5px] font-bold disabled:opacity-50">
              {busy ? 'Please wait…' : 'Yes, accept it'}
            </button>
            <button onClick={() => setConfirming(false)} className="rounded-full border border-line px-3 py-1.5 text-[12.5px] font-bold text-text-mute">
              Not yet
            </button>
          </div>
        </div>
      )}
      {rejecting && (
        <div className="mt-2">
          <div className="mb-1.5 flex flex-col gap-1">
            <label className="flex items-center gap-2">
              <input type="radio" name={`rej-${order.id}`} checked={code === 'not_as_described'} onChange={() => setCode('not_as_described')} />
              The item isn&apos;t what was described
            </label>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name={`rej-${order.id}`}
                disabled={!noShowOpen}
                checked={code === 'seller_not_there'}
                onChange={() => setCode('seller_not_there')}
              />
              I went and nobody was there
            </label>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name={`rej-${order.id}`}
                disabled={!noShowOpen}
                checked={code === 'seller_refused'}
                onChange={() => setCode('seller_refused')}
              />
              The seller was there but wouldn&apos;t show or sell it to me
            </label>
            {!noShowOpen && (
              <p className="pl-6 text-[11.5px] text-text-mute">
                Available once the time you told the seller (&quot;I&apos;m coming&quot;) has passed.
              </p>
            )}
            <label className="flex items-center gap-2">
              <input type="radio" name={`rej-${order.id}`} checked={code === 'other'} onChange={() => setCode('other')} />
              Another reason
            </label>
          </div>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={500}
            rows={2}
            placeholder={code === 'seller_not_there' ? 'Optional: when did you go?' : code === 'seller_refused' ? 'What did the seller say or do?' : 'What is wrong with it?'}
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-base text-text focus:border-mark focus:outline-none sm:text-[13px]"
          />
          {(code === 'seller_not_there' || code === 'seller_refused') && (
            <label className="mt-1.5 block text-text-mute">
              Take a photo of the place you went to (the front of the building or the address) so the seller and our team can see it:
              <input
                type="file"
                accept="image/*"
                capture="environment"
                onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
                className="mt-1 block w-full text-[12px]"
              />
            </label>
          )}
          <div className="mt-1.5 flex gap-2">
            <button
              onClick={() =>
                run(async () => {
                  const url = (code === 'seller_not_there' || code === 'seller_refused') && photo ? (await uploadFile(photo)).url : undefined;
                  return collectReject(order.id, code, reason.trim(), url);
                })
              }
              disabled={busy || (code !== 'seller_not_there' && reason.trim().length < 3) || ((code === 'seller_not_there' || code === 'seller_refused') && (!noShowOpen || !photo))}
              className="rounded-full btn-neutral px-3 py-1.5 text-[12.5px] font-bold disabled:opacity-50"
            >
              {busy ? 'Please wait…' : 'Confirm reject'}
            </button>
            <button onClick={() => setRejecting(false)} className="rounded-full border border-line px-3 py-1.5 text-[12.5px] font-bold text-text-mute">
              Back
            </button>
          </div>
        </div>
      )}
      {error && <p className="mt-1 text-red-600">{error}</p>}
    </div>
  );
}
