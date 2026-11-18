'use client';

import type { ApiProduct } from '@/lib/api';
import { apiProductToProduct } from '@/lib/adapters';
import { formatMoney } from '@/lib/money';
import type { Product } from '@/lib/types';

interface LiveProductsProps {
  products: ApiProduct[];
  // "overlay" sits on the video (light on dark glass); "panel" sits on the page's own surface.
  tone: 'overlay' | 'panel';
  // The host sees what they are showing but has nothing to buy.
  disabled?: boolean;
  // Opens the product, where size and colour are picked and Buy now / Add to cart live. Everything stays on top of the live.
  onSelect?: (product: Product) => void;
}

// The products a live is showing, as a scrolling row of cards each with a Buy button.
export function LiveProducts({ products, tone, disabled, onSelect }: LiveProductsProps) {
  if (products.length === 0) return null;
  const overlay = tone === 'overlay';
  return (
    <div className="flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {products.map((p) => {
        const price = parseFloat(p.sale_price ?? p.price);
        const img = [...p.images].sort((a, b) => a.position - b.position)[0]?.url;
        const open = () => onSelect?.(apiProductToProduct(p));
        return (
          <div
            key={p.id}
            role={disabled ? undefined : 'button'}
            tabIndex={disabled ? undefined : 0}
            onClick={disabled ? undefined : open}
            onKeyDown={(e) => !disabled && (e.key === 'Enter' || e.key === ' ') && open()}
            className={`flex w-[236px] shrink-0 items-center gap-2 rounded-xl p-1.5 ${
              overlay ? 'bg-black/55 backdrop-blur-md' : 'bg-panel'
            } ${disabled ? '' : 'cursor-pointer active:scale-[0.98]'}`}
          >
            <span className="h-12 w-12 shrink-0 overflow-hidden rounded-lg bg-box">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {img && <img src={img} alt="" className="h-full w-full object-cover" />}
            </span>
            <span className="min-w-0 flex-1">
              <span className={`line-clamp-2 break-words text-[12.5px] font-bold leading-tight ${overlay ? 'text-white' : 'text-text'}`}>{p.name}</span>
              <span className={`block text-[12px] font-extrabold ${overlay ? 'text-white/85' : 'text-accent-ink'}`}>
                {formatMoney(price, p.currency)}
              </span>
            </span>
            {!disabled && (
              <span className="brand-gradient shrink-0 whitespace-nowrap rounded-full px-3 py-1.5 text-[11.5px] font-extrabold text-white">Buy</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
