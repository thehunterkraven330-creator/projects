'use client';

import { Radio, Zap } from 'lucide-react';
import { clock } from '@/lib/useCountdown';

interface Props {
  kind: 'live' | 'sale';
  eventAt: string;
  remaining: number | null; // from useCountdown(eventAt)
  percent?: number | null; // the product's real discount, for a sale
  onOpenLive: () => void;
}

// The strip a seller's announcement story carries: "Live at 8:00 PM" with a countdown, or "Flash sale -20%" with the time left.
// The times are the seller's; the price is the product's own, shown beside it in the story.
export function StoryAnnouncement({ kind, eventAt, remaining, percent, onOpenLive }: Props) {
  const over = remaining !== null && remaining <= 0;
  if (kind === 'live') {
    const time = new Date(eventAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    return (
      <div className="pointer-events-auto flex items-center gap-2.5 rounded-2xl bg-black/65 p-2.5 text-white backdrop-blur">
        <span className="brand-scan flex h-9 w-9 shrink-0 items-center justify-center rounded-full">
          <Radio size={18} aria-hidden="true" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[13px] font-extrabold">{over ? 'Going live now' : `Live at ${time}`}</span>
          <span className="block text-[12px] text-white/70">{over ? 'Join them' : remaining === null ? '' : `Starts in ${clock(remaining)}`}</span>
        </span>
        <button type="button" onClick={onOpenLive} className="brand-gradient shrink-0 rounded-full px-3.5 py-2 text-[12.5px] font-bold text-white">
          {over ? 'Watch live' : 'Open lives'}
        </button>
      </div>
    );
  }
  return (
    <div className="pointer-events-auto flex items-center gap-2.5 rounded-2xl bg-black/65 p-2.5 text-white backdrop-blur">
      <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${over ? 'bg-white/20' : 'brand-scan'}`}>
        <Zap size={18} aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[13px] font-extrabold">{over ? 'Sale ended' : `Flash sale${percent ? ` · ${percent}% off` : ''}`}</span>
        <span className="block text-[12px] text-white/70">{over ? 'This offer is over' : remaining === null ? '' : `Ends in ${clock(remaining)}`}</span>
      </span>
    </div>
  );
}
