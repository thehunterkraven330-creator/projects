'use client';

import { createPortal } from 'react-dom';
import { ChevronLeft } from 'lucide-react';
import type { Product } from '@/lib/types';
import { formatMoney } from '@/lib/money';
import { unitPrice } from '@/lib/price';
import { portalTarget } from '@/lib/portal';
import { ProductThumbnail } from './Thumbnails';

interface Props {
  picture: string | null; // the picture the person scanned (a local preview, never uploaded from here)
  products: Product[];
  byColour: boolean;
  onSelectProduct: (product: Product) => void;
  onClose: () => void;
}

// Their own screen for "products that look like your picture": shown when a screenshot or photo matches no video.
export function SimilarProductsScreen({ picture, products, byColour, onSelectProduct, onClose }: Props) {
  const target = portalTarget();
  if (!target) return null;
  return createPortal(
    <div role="dialog" aria-label="Products that look like your picture" className="fixed inset-0 z-[65] flex flex-col bg-panel">
      <div className="flex shrink-0 items-center gap-2 border-b border-line bg-surface px-3 py-2.5">
        <button type="button" onClick={onClose} aria-label="Back" className="flex h-9 w-9 items-center justify-center rounded-full bg-panel text-text">
          <ChevronLeft size={20} />
        </button>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15px] font-extrabold text-text">Looks like your picture</p>
          <p className="text-[12px] text-text-mute">{products.length} {products.length === 1 ? 'product' : 'products'}</p>
        </div>
        {picture && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={picture} alt="Your picture" className="h-10 w-10 shrink-0 rounded-lg object-cover" />
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-6 pt-3">
        <p className="mb-3 text-[12.5px] leading-snug text-text-mute">
          No video here matches your picture. {byColour ? 'These are matched by colour and shape, so check each one is what you want.' : 'These are matched by what the item looks like.'}
        </p>
        <div className="mx-auto grid max-w-[900px] grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {products.map((p) => (
            <button key={p.id} type="button" onClick={() => onSelectProduct(p)} className="min-w-0 text-left" aria-label={`${p.name}, ${formatMoney(unitPrice(p))}`}>
              <span className="relative block aspect-[3/4] overflow-hidden rounded-2xl bg-box">
                <ProductThumbnail product={p} className="absolute inset-0 h-full w-full object-cover" />
              </span>
              <span className="mt-1.5 block truncate text-[13px] font-semibold text-text">{p.name}</span>
              <span className="block text-[14px] font-extrabold text-text">{formatMoney(unitPrice(p))}</span>
            </button>
          ))}
        </div>
      </div>
    </div>,
    target,
  );
}
