'use client';

import { useEffect, useState } from 'react';
import { Check, Video } from 'lucide-react';
import { ApiError, listMyMerchantProducts, startLive, type ApiLiveJoin, type ApiProduct } from '@/lib/api';
import { formatMoney } from '@/lib/money';
import { LiveRoom } from './LiveRoom';
import { PageHeader } from './PageHeader';

const MAX_PRODUCTS = 12;

interface GoLiveProps {
  onBack: () => void;
  onNeedLogin: () => void;
}

// Merchant side: name the live, pick the products to show, start. Once it starts this becomes the broadcast screen.
export function GoLive({ onBack, onNeedLogin }: GoLiveProps) {
  const [title, setTitle] = useState('');
  const [products, setProducts] = useState<ApiProduct[] | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [join, setJoin] = useState<ApiLiveJoin | null>(null);

  useEffect(() => {
    listMyMerchantProducts()
      .then(setProducts)
      .catch(() => setProducts([]));
  }, []);

  if (join) return <LiveRoom hostJoin={join} onBack={onBack} onNeedLogin={onNeedLogin} />;

  const toggle = (id: string) =>
    setPicked((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : prev.length >= MAX_PRODUCTS ? prev : [...prev, id]));

  const start = async () => {
    if (!title.trim() || starting) return;
    setStarting(true);
    setError(null);
    try {
      setJoin(await startLive(title.trim(), picked));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't start the live. Check your connection and try again.");
      setStarting(false);
    }
  };

  return (
    <div className="flex h-full flex-col bg-surface">
      <PageHeader title="Go live" onBack={onBack} backLabel="Back to New Arrivals" />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-lg px-4 py-5 lg:px-0 lg:py-8">
          <label className="block text-[12px] font-extrabold uppercase tracking-[0.12em] text-text-mute" htmlFor="live-title">
            What are you showing?
          </label>
          <input
            id="live-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={120}
            placeholder="e.g. New sneakers just landed"
            className="mt-2 w-full rounded-xl2 bg-box px-4 py-3 text-[15px] text-text outline-none placeholder:text-text-mute"
          />

          <p className="mt-6 text-[12px] font-extrabold uppercase tracking-[0.12em] text-text-mute">
            Products to show ({picked.length}/{MAX_PRODUCTS})
          </p>
          <p className="mt-1 text-[12.5px] text-text-mute">Viewers can tap these to open them while you talk. You can go live without any.</p>

          {products === null && <p className="py-6 text-[13px] text-text-mute">Loading your products…</p>}
          {products !== null && products.length === 0 && (
            <p className="py-6 text-[13px] text-text-mute">You haven&apos;t added any products yet. You can still go live and talk.</p>
          )}
          <div className="mt-3 flex flex-col gap-1.5">
            {products?.map((p) => {
              const on = picked.includes(p.id);
              const img = [...p.images].sort((a, b) => a.position - b.position)[0]?.url;
              return (
                <button
                  key={p.id}
                  onClick={() => toggle(p.id)}
                  className={`flex items-center gap-3 rounded-2xl p-2.5 text-left ${on ? 'bg-panel ring-2 ring-accent' : 'bg-panel'}`}
                >
                  <span className="h-12 w-12 shrink-0 overflow-hidden rounded-xl bg-box">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    {img && <img src={img} alt="" className="h-full w-full object-cover" />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[14px] font-bold text-text">{p.name}</span>
                    <span className="block text-[12.5px] font-semibold text-text-mute">
                      {formatMoney(parseFloat(p.sale_price ?? p.price), p.currency)}
                    </span>
                  </span>
                  <span
                    className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${on ? 'bg-accent text-on-accent' : 'border border-line'}`}
                  >
                    {on && <Check size={14} strokeWidth={3} />}
                  </span>
                </button>
              );
            })}
          </div>

          {error && <p className="mt-4 text-[13px] font-bold text-danger">{error}</p>}
          <button
            onClick={() => void start()}
            disabled={!title.trim() || starting}
            className="brand-gradient mt-6 flex w-full items-center justify-center gap-2 rounded-full py-3.5 text-[14.5px] font-extrabold text-white disabled:opacity-45"
          >
            <Video size={17} /> {starting ? 'Starting…' : 'Start live'}
          </button>
          <p className="mt-3 text-center text-[12px] text-text-mute">Your browser will ask to use the camera and microphone.</p>
        </div>
      </div>
    </div>
  );
}
