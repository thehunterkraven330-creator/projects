'use client';

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, Plus, X } from 'lucide-react';
import type { Product } from '@/lib/types';
import { apiProductToProduct } from '@/lib/adapters';
import { clickSponsoredTwin, getSponsoredTwinsForProduct, revealSponsoredTwin } from '@/lib/api';
import { forgetSponsored, rememberSponsored } from '@/lib/sponsoredAttribution';
import { ADDED_EVENT, quietly, type AddedDetail } from '@/lib/addOnOffer';
import { unitPrice } from '@/lib/price';
import { formatMoney } from '@/lib/money';
import { portalTarget } from '@/lib/portal';
import { ProductThumbnail } from './Thumbnails';

interface Props {
  view: string; // the sheet stays away from the cart screen itself (it has its own add-on card)
  cartProductIds: string[];
  onAddToCart: (product: Product, color: string, size: string) => void;
  onSelectProduct: (product: Product) => void;
  onViewCart: () => void;
}

type Tile = { id: string; product: Product };

// After a shopper taps Add to cart: a small, non-blocking sheet ("Added to cart" + what goes with it). It is the natural
// pause for one more item. It never appears for Buy now, for adds made from an add-on card, or when nothing goes with the item.
export function AddedToCartSheet({ view, cartProductIds, onAddToCart, onSelectProduct, onViewCart }: Props) {
  const [name, setName] = useState('');
  const [tiles, setTiles] = useState<Tile[]>([]);
  const [open, setOpen] = useState(false);
  const [added, setAdded] = useState<Record<string, boolean>>({});
  const inCart = useRef<string[]>([]);
  const latest = useRef(0);
  const shown = useRef<Set<string>>(new Set());
  inCart.current = cartProductIds;

  useEffect(() => {
    const onAdded = (e: Event) => {
      const d = (e as CustomEvent<AddedDetail>).detail;
      if (!d?.productId) return;
      const mine = ++latest.current;
      getSponsoredTwinsForProduct(d.productId)
        .then((rows) => {
          if (mine !== latest.current) return; // a newer add replaced this one
          const next = (rows ?? [])
            .map((r) => ({ id: r.id, product: apiProductToProduct(r.product) }))
            .filter((t) => t.product.inStock && t.product.id !== d.productId && !inCart.current.includes(t.product.id))
            .slice(0, 8);
          if (next.length === 0) return;
          setName(d.name);
          setTiles(next);
          setAdded({});
          setOpen(true);
          for (const t of next) {
            if (shown.current.has(t.id)) continue;
            shown.current.add(t.id);
            revealSponsoredTwin(t.id).catch(() => {});
          }
        })
        .catch(() => {});
    };
    window.addEventListener(ADDED_EVENT, onAdded);
    return () => window.removeEventListener(ADDED_EVENT, onAdded);
  }, []);

  // Gone when the shopper moves on to the cart, and after a while if nobody touches it.
  useEffect(() => {
    if (view === 'cart') setOpen(false);
  }, [view]);
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => setOpen(false), 14000);
    return () => clearTimeout(t);
  }, [open, added]);

  if (!open || tiles.length === 0 || view === 'cart') return null;
  const target = portalTarget();
  if (!target) return null;

  const needsChoice = (p: Product) => p.sizes.length > 1;
  const toggle = (t: Tile) => {
    const p = t.product;
    if (added[t.id]) {
      forgetSponsored(p.id);
      window.dispatchEvent(new CustomEvent('lumin:cart-undo', { detail: { productId: p.id, color: p.colors[0] ?? '', size: p.sizes.length === 1 ? p.sizes[0] : '' } }));
      setAdded((m) => ({ ...m, [t.id]: false }));
      return;
    }
    if (needsChoice(p)) {
      setOpen(false);
      onSelectProduct(p); // a size is a real choice: open the product instead of guessing
      return;
    }
    rememberSponsored(p.id, t.id);
    clickSponsoredTwin(t.id, undefined, 'cart', undefined, undefined).catch(() => {});
    quietly(() => onAddToCart(p, p.colors[0] ?? '', p.sizes.length === 1 ? p.sizes[0] : ''));
    setAdded((m) => ({ ...m, [t.id]: true }));
  };
  const count = Object.values(added).filter(Boolean).length;

  return createPortal(
    <div
      role="dialog"
      aria-label="Added to cart"
      className="dock-shadow fixed inset-x-0 bottom-0 z-[95] mx-auto w-full max-w-[560px] animate-[sheetUp_320ms_cubic-bezier(0.22,1,0.36,1)] rounded-t-[20px] bg-[rgb(var(--c-dock))] px-3 pb-[max(12px,env(safe-area-inset-bottom))] pt-3"
    >
      <div className="flex items-center gap-2">
        <span className="fill-violet flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-white">
          <Check size={14} strokeWidth={3} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[14px] font-extrabold text-ink">Added to cart</p>
          <p className="truncate text-[12px] text-mute">Goes well with {name || 'it'}</p>
        </div>
        <button type="button" onClick={() => setOpen(false)} aria-label="Close" className="flex h-8 w-8 items-center justify-center rounded-full text-mute">
          <X size={18} />
        </button>
      </div>

      <div className="-mx-3 mt-2.5 flex gap-2.5 overflow-x-auto px-3 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {tiles.map((t) => (
          <div key={t.id} className="w-[92px] shrink-0">
            <div className="relative aspect-[3/4] overflow-hidden rounded-xl bg-surface">
              <button type="button" onClick={() => { setOpen(false); onSelectProduct(t.product); }} aria-label={`View ${t.product.name}`} className="absolute inset-0">
                <ProductThumbnail product={t.product} className="h-full w-full object-cover" />
              </button>
              <button
                type="button"
                onClick={() => toggle(t)}
                aria-label={added[t.id] ? `Remove ${t.product.name}` : `Add ${t.product.name}`}
                className={`absolute bottom-1.5 right-1.5 flex h-7 w-7 items-center justify-center rounded-full shadow ${added[t.id] ? 'brand-gradient text-white' : 'bg-white text-black'}`}
              >
                {added[t.id] ? <Check size={15} strokeWidth={3} /> : <Plus size={16} strokeWidth={2.6} />}
              </button>
            </div>
            <p className="mt-1 truncate text-[11px] font-semibold text-ink">{t.product.name}</p>
            <p className="text-[12px] font-extrabold text-ink">{formatMoney(unitPrice(t.product))}</p>
          </div>
        ))}
      </div>

      <div className="mt-2.5 flex gap-2">
        <button type="button" onClick={() => setOpen(false)} className="flex-1 rounded-xl bg-surface py-3 text-[14px] font-bold text-ink">
          Keep shopping
        </button>
        <button type="button" onClick={() => { setOpen(false); onViewCart(); }} className="brand-gradient flex-1 rounded-xl py-3 text-[14px] font-bold text-white">
          View cart{count > 0 ? ` · ${count} more` : ''}
        </button>
      </div>
    </div>,
    target,
  );
}
