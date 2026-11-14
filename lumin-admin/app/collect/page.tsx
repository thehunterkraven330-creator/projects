'use client';

import { useEffect, useState } from 'react';
import { AdminShell } from '@/components/AdminShell';
import { ApiError, decideNoShow, getCollectOverview, type ApiCollectOrder, type ApiCollectSeller, type ApiNoShow, type CollectOutcome } from '@/lib/api';

const TABS: { key: CollectOutcome | 'all'; label: string }[] = [
  { key: 'rejected', label: 'Rejected' },
  { key: 'seller_not_there', label: 'Seller was not there' },
  { key: 'seller_refused', label: 'Seller refused' },
  { key: 'not_collected', label: 'Not collected' },
  { key: 'waiting', label: 'Waiting' },
  { key: 'accepted', label: 'Accepted' },
  { key: 'all', label: 'All' },
];

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : '');

export default function CollectPage() {
  const [tab, setTab] = useState<CollectOutcome | 'all'>('rejected');
  const [orders, setOrders] = useState<ApiCollectOrder[]>([]);
  const [sellers, setSellers] = useState<ApiCollectSeller[]>([]);
  const [noshows, setNoshows] = useState<ApiNoShow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    getCollectOverview()
      .then((r) => {
        setOrders(r.orders);
        setSellers(r.sellers);
        setNoshows(r.noshows);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load.'))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);
  const decide = (id: string, d: 'confirm' | 'dismiss') => {
    setError(null);
    decideNoShow(id, d)
      .then(load)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'That failed.'));
  };
  const open = noshows.filter((n) => n.status === 'claimed' || n.status === 'disputed');

  const shown = orders.filter((o) => tab === 'all' || o.outcome === tab);
  const flagged = sellers.filter((s) => s.rejected + s.seller_not_there + s.seller_refused + s.not_collected > 0);

  return (
    <AdminShell>
      <p className="mb-1 text-[20px] font-bold text-text">Collect in person</p>
      <p className="mb-5 text-[13px] text-text-mute">
        Machines and bulk goods the buyer inspects at the seller. Look here for sellers whose buyers keep rejecting the item or finding nobody
        there. These numbers are for your judgement: nothing is punished automatically.
      </p>
      {error && <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>}

      {open.length > 0 && (
        <div className="mb-6 rounded-xl border border-line bg-white p-4">
          <p className="text-[13.5px] font-bold text-text">Claims against sellers to decide (nobody there, or refused) ({open.length})</p>
          <p className="mb-2 text-[12px] text-text-mute">
            The buyer was already refunded. Confirm adds a strike to the seller; dismiss adds nothing. Compare the two photos and the times.
          </p>
          {open.map((n) => (
            <div key={n.id} className="border-t border-line py-3 text-[12.5px]">
              <p className="font-bold text-text">
                {n.product_name ?? 'Order'} · {n.seller_name ?? 'seller'} · buyer {n.buyer_name ?? '?'} ·{' '}
                {n.kind === 'refused' ? 'says the seller refused to show or sell it' : 'says nobody was there'}
              </p>
              <p className="text-text-mute">
                Buyer planned {when(n.planned_for)} · claim made {when(n.created_at)} · seller {n.seller_replied ? 'replied' : 'has not replied'}
              </p>
              <div className="mt-2 grid gap-3 sm:grid-cols-2">
                <div>
                  <p className="font-bold">Buyer</p>
                  {n.buyer_note && <p>{n.buyer_note}</p>}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={n.buyer_photo_url} alt="Photo from the buyer" className="mt-1 max-h-48 rounded-lg border border-line" />
                </div>
                <div>
                  <p className="font-bold">Seller</p>
                  {n.seller_note ? <p>{n.seller_note}</p> : <p className="text-text-mute">No reply.</p>}
                  {n.seller_photo_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={n.seller_photo_url} alt="Photo from the seller" className="mt-1 max-h-48 rounded-lg border border-line" />
                  )}
                </div>
              </div>
              <div className="mt-2 flex gap-2">
                <button onClick={() => decide(n.id, 'confirm')} className="rounded-lg bg-ink px-3 py-1.5 text-[12px] font-bold text-white">
                  Confirm: add a strike
                </button>
                <button onClick={() => decide(n.id, 'dismiss')} className="rounded-lg border border-line px-3 py-1.5 text-[12px] font-bold text-text-mute">
                  Dismiss
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {flagged.length > 0 && (
        <div className="mb-6 overflow-x-auto rounded-xl border border-line bg-white">
          <table className="w-full text-left text-[12.5px]">
            <thead className="text-text-mute">
              <tr>
                <th className="px-3 py-2">Seller</th>
                <th className="px-3 py-2">Accepted</th>
                <th className="px-3 py-2">Rejected</th>
                <th className="px-3 py-2">Not there</th>
                <th className="px-3 py-2">Refused</th>
                <th className="px-3 py-2">Strikes</th>
                <th className="px-3 py-2">Not collected</th>
              </tr>
            </thead>
            <tbody>
              {flagged.map((s) => (
                <tr key={s.seller_id} className="border-t border-line">
                  <td className="px-3 py-2 font-bold text-text">{s.seller_name ?? s.seller_id}</td>
                  <td className="px-3 py-2">{s.accepted}</td>
                  <td className="px-3 py-2">{s.rejected}</td>
                  <td className="px-3 py-2">{s.seller_not_there}</td>
                  <td className="px-3 py-2">{s.seller_refused}</td>
                  <td className="px-3 py-2 font-bold">{s.no_show_strikes}</td>
                  <td className="px-3 py-2">{s.not_collected}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mb-4 flex flex-wrap gap-2">
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`rounded-full border px-3.5 py-1.5 text-[12px] font-bold ${tab === key ? 'border-hot-pink bg-ink text-white' : 'border-line bg-white text-text-mute'}`}
          >
            {label}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-[13px] text-text-mute">Loading…</p>
      ) : shown.length === 0 ? (
        <p className="text-[13px] text-text-mute">Nothing here.</p>
      ) : (
        <div className="flex flex-col gap-2.5">
          {shown.map((o) => (
            <div key={o.order_id} className="rounded-xl border border-line bg-white p-3.5 text-[12.5px]">
              <p className="font-bold text-text">
                {o.product_name ?? 'Order'} · {o.seller_name ?? 'seller'} · buyer {o.buyer_name ?? '?'}
              </p>
              <p className="mt-0.5 text-text-mute">
                {o.order_id} · placed {when(o.created_at)}
                {o.outcome === 'waiting' && o.deadline ? ` · must collect before ${when(o.deadline)}` : ''}
              </p>
              {o.reason && <p className="mt-1 text-text">Buyer said: {o.reason}</p>}
            </div>
          ))}
        </div>
      )}
    </AdminShell>
  );
}
