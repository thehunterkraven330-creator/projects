'use client';

import { useState } from 'react';
import { PriceTag } from './PriceTag';
import type { Product } from '@/lib/types';
import { ProductThumbnail } from './Thumbnails';
import { CollectBadge } from './CollectBadge';

// A product in a browse list. Tapping the tile opens the full product detail screen. When the list passes `onAddToCart`
// the tile also has an "Add to cart" button under the price: a product with nothing to choose (at most one colour and
// one size) goes straight into the cart; one with a choice says "Choose options" and opens the detail screen, so nobody
// gets a size they didn't pick. Below the sm breakpoint it lays out as a single row (thumbnail left, text right); from sm
// up it switches to the stacked card used in the multi-column grid.
interface ProductTileProps {
  product: Product;
  onSelectProduct: (product: Product) => void;
  onAddToCart?: (product: Product, color: string, size: string) => void;
}

export function ProductTile({ product, onSelectProduct, onAddToCart }: ProductTileProps) {
  const [justAdded, setJustAdded] = useState(false);
  const hasChoice = product.colors.length > 1 || product.sizes.length > 1;

  const addToCart = () => {
    if (!product.inStock || justAdded || !onAddToCart) return;
    if (hasChoice) {
      onSelectProduct(product);
      return;
    }
    onAddToCart(product, product.colors[0] ?? '', product.sizes[0] ?? '');
    setJustAdded(true);
    setTimeout(() => setJustAdded(false), 1600);
  };

  return (
    <div className="flex flex-row gap-3 rounded-xl border border-line bg-surface p-2.5 text-left sm:flex-col sm:gap-2 sm:p-3">
      <button onClick={() => onSelectProduct(product)} className="block h-24 w-24 shrink-0 overflow-hidden rounded-lg bg-box text-left sm:h-auto sm:w-full sm:aspect-square" aria-label={product.name}>
        <ProductThumbnail product={product} />
      </button>
      <div className="flex min-w-0 flex-1 flex-col justify-center gap-1 sm:flex-none sm:justify-start">
        <button onClick={() => onSelectProduct(product)} className="block min-w-0 text-left">
          <span className="line-clamp-2 block text-[13.5px] leading-snug text-text sm:text-[12.5px] lg:text-sm">{product.name}</span>
          <span className="block">
            <PriceTag product={product} className="text-[18px] sm:text-[17px] lg:text-[18px]" showPercent={false} />
          </span>
        </button>
        {product.collectInPerson && <CollectBadge from={product.collectFrom} className="self-start" />}
        {onAddToCart && (
          <button
            onClick={addToCart}
            disabled={!product.inStock || justAdded}
            className="mt-1 self-start rounded-md bg-panel px-3 py-1.5 text-[12.5px] font-semibold text-text disabled:opacity-60 sm:self-stretch sm:text-center"
          >
            {!product.inStock ? 'Out of stock' : justAdded ? 'Added ✓' : hasChoice ? 'Choose options' : 'Add to cart'}
          </button>
        )}
      </div>
    </div>
  );
}
