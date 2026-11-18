'use client';

import { useState } from 'react';
import { ChevronLeft } from 'lucide-react';
import type { ApiLiveStream } from '@/lib/api';
import type { Product } from '@/lib/types';
import { LiveProducts } from './LiveProducts';
import { UserAvatar } from './UserAvatar';

interface LiveReplayProps {
  stream: ApiLiveStream;
  onBack: () => void;
  onSelectProduct: (product: Product) => void;
}

// A recorded live: plays the recording with the usual video controls, and the products shown in it stay buyable underneath.
export function LiveReplay({ stream, onBack, onSelectProduct }: LiveReplayProps) {
  const [failed, setFailed] = useState(false);
  return (
    <div className="dark relative flex h-full w-full flex-col bg-black">
      <video
        src={stream.replay_url ?? undefined}
        controls
        autoPlay
        playsInline
        onError={() => setFailed(true)}
        className="min-h-0 flex-1 bg-black object-contain"
      />
      <div className="absolute inset-x-0 top-0 z-10 flex items-center gap-2 bg-gradient-to-b from-black/70 to-transparent px-3 pb-6 pt-[max(12px,env(safe-area-inset-top))]">
        <button
          onClick={onBack}
          aria-label="Back"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-black/55 text-white backdrop-blur-sm"
        >
          <ChevronLeft size={20} />
        </button>
        <span className="h-9 w-9 shrink-0 overflow-hidden rounded-full">
          <UserAvatar url={stream.host_avatar_url} name={stream.host_name} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13.5px] font-extrabold text-white">{stream.title}</span>
          <span className="block truncate text-[11.5px] text-white/75">
            Replay · {stream.business_name ?? stream.host_name}
          </span>
        </span>
      </div>
      {failed && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-black/85 px-8 text-center">
          <p className="text-[14px] font-bold text-white">This replay isn&apos;t ready yet</p>
          <p className="text-[12.5px] text-white/70">Recordings take a minute or two to finish after a live ends. Try again shortly.</p>
          <button onClick={onBack} className="rounded-full bg-white px-5 py-2 text-[13px] font-extrabold text-ink">
            Back
          </button>
        </div>
      )}
      {stream.products.length > 0 && (
        <div className="shrink-0 bg-black px-3 pb-[max(12px,env(safe-area-inset-bottom))] pt-2">
          <LiveProducts products={stream.products} tone="overlay" onSelect={onSelectProduct} />
        </div>
      )}
    </div>
  );
}
