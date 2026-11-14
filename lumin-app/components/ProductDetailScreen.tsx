'use client';

import { PriceTag } from './PriceTag';
import { unitPrice } from '@/lib/price';
import { useEffect, useRef, useState } from 'react';
import { Tag, X } from 'lucide-react';
import { ApiError } from '@/lib/api';
import type { Product } from '@/lib/types';
import { PageHeader } from './PageHeader';
import { CollectBanner } from './CollectBadge';
import { ProductTile } from './ProductTile';
import { SponsoredTwinCard } from './SponsoredTwinCard';
import { formatMoney } from '@/lib/money';

interface ProductDetailScreenProps {
  product: Product;
  categoryName: string;
  backLabel: string;
  onBack: () => void;
  // Resolves with what happened ('placed' only once the payment is confirmed) so the button can show the truth.
  onBuyNow: (product: Product, color: string, size: string, discountCode?: string) => void | Promise<unknown>;
  onAddToCart: (product: Product, color: string, size: string) => void;
  // Read-only check via POST /discounts/preview against this one
  // product's price — the Buy Now equivalent of CartScreen's own
  // onPreviewDiscount, kept as a separate prop/call rather than reusing
  // that one since the two check against different things (a cart
  // subtotal vs. a single product×quantity). Not offered on
  // ProductCard's own quick-buy tile — see this component's header
  // comment for why a text field doesn't belong on a one-tap button.
  onPreviewDiscount: (code: string, productId: string) => Promise<{ code: string; discountAmount: number }>;
  // Other products from the same banner/category as this one — empty
  // when none exist (e.g. a shop-feed product with no category at all),
  // in which case the section below just doesn't render.
  relatedProducts: Product[];
  onSelectRelatedProduct: (product: Product) => void;
}

// Reached from a category tile, a search result, or now a shop-feed
// product card — the tile/card itself is browse-only (no purchase actions
// on it directly for the category flow; the shop card keeps its own quick
// actions too, this is just the deeper look), and this is where full
// photos, description, and color/size selection live. Photos are honest
// gray placeholders when a product has none, same convention as every
// other thumbnail in this app — there's no real upload pipeline to fake
// otherwise.
export function ProductDetailScreen({
  product,
  categoryName,
  backLabel,
  onBack,
  onBuyNow,
  onAddToCart,
  onPreviewDiscount,
  relatedProducts,
  onSelectRelatedProduct,
}: ProductDetailScreenProps) {
  const photos =
    product.images && product.images.length > 0 ? product.images : [product.imageUrl || '/images/placeholder.svg'];
  const [activePhoto, setActivePhoto] = useState(0);
  const [selectedColor, setSelectedColor] = useState(product.colors[0]);
  const [selectedSize, setSelectedSize] = useState(product.sizes[0]);
  const [justOrdered, setJustOrdered] = useState(false);
  const [buying, setBuying] = useState(false);
  const [justAdded, setJustAdded] = useState(false);

  // Discount code — same shape as CartScreen's own (see that component
  // for the fuller reasoning): appliedDiscount only ever comes from a
  // successful onPreviewDiscount call, never guessed client-side, and
  // resets automatically for a new product without any manual reset —
  // this whole component remounts fresh per product.id (see the
  // scrollRef effect's own comment on that key), so there's no stale
  // "applied" state to carry from one product to the next.
  const [discountInput, setDiscountInput] = useState('');
  const [appliedDiscount, setAppliedDiscount] = useState<{ code: string; discountAmount: number } | null>(
    null,
  );
  const [checkingDiscount, setCheckingDiscount] = useState(false);
  const [discountError, setDiscountError] = useState<string | null>(null);

  const handleApplyDiscount = async () => {
    const code = discountInput.trim();
    if (!code || checkingDiscount) return;
    setCheckingDiscount(true);
    setDiscountError(null);
    try {
      const result = await onPreviewDiscount(code, product.id);
      setAppliedDiscount(result);
    } catch (err) {
      setAppliedDiscount(null);
      setDiscountError(err instanceof ApiError ? err.message : "Couldn't check that code — try again.");
    } finally {
      setCheckingDiscount(false);
    }
  };

  const handleRemoveDiscount = () => {
    setAppliedDiscount(null);
    setDiscountInput('');
    setDiscountError(null);
  };

  // Same threshold/logic as ProductCard's own lowStock — see its comment.
  const lowStock =
    product.inStock && typeof product.stockQuantity === 'number' && product.stockQuantity <= 5;

  // Picking a related product swaps this screen to a new product — the
  // parent keys this component on product.id, so React remounts fresh on
  // every switch instead of reusing the instance. That already resets
  // local state (color/size/photo picks) and scroll position for a plain
  // instant reset; this effect is just a safety net (and adds the smooth
  // scroll) in case something upstream ever renders this without a key.
  const scrollRef = useRef<HTMLDivElement>(null);
  // The buy buttons in the page; when they scroll out of view a bar with the same two buttons stays at the bottom (phones).
  const buyRowRef = useRef<HTMLDivElement>(null);
  const [showBar, setShowBar] = useState(false);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  }, [product.id]);

  useEffect(() => {
    const row = buyRowRef.current;
    if (!row || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver(([e]) => setShowBar(!e.isIntersecting), { root: scrollRef.current, threshold: 0 });
    io.observe(row);
    return () => io.disconnect();
  }, [product.id]);

  const buyLabel =
    justOrdered
    ? 'Order placed ✓'
    : buying
      ? 'Waiting for payment…'
      : !product.inStock
      ? 'Out of stock'
      : appliedDiscount
        ? `Buy now — ${formatMoney(Math.max(unitPrice(product) - appliedDiscount.discountAmount, 0))}`
        : 'Buy now';

  const handleBuyNow = async () => {
    if (!product.inStock || buying) return;
    setBuying(true);
    try {
      const result = await onBuyNow(product, selectedColor, selectedSize, appliedDiscount?.code);
      if (result === 'placed') {
        setJustOrdered(true);
        setTimeout(() => setJustOrdered(false), 2400);
      }
    } finally {
      setBuying(false);
    }
  };

  const handleAddToCart = () => {
    if (!product.inStock) return;
    onAddToCart(product, selectedColor, selectedSize);
    setJustAdded(true);
    setTimeout(() => setJustAdded(false), 1600);
  };

  return (
    <div className="flex h-full flex-col bg-panel">
      <PageHeader title={product.name} onBack={onBack} backLabel={backLabel} />
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 py-4 lg:px-0 lg:py-6">
          <div className="lg:flex lg:gap-8">
            {/* Gallery */}
            <div className="lg:w-1/2 lg:shrink-0">
              <div className="relative aspect-square w-full overflow-hidden rounded-2xl bg-box">
                {/* eslint-disable-next-line @next/next/no-img-element -- blob:
                    URLs from the merchant's file picker aren't compatible
                    with next/image's optimizer, so a plain img tag is used
                    for every photo here, not just uploaded ones. */}
                <img src={photos[activePhoto]} alt={product.name} className="h-full w-full object-cover" />
                {photos.length > 1 && (
                  <span className="absolute bottom-2.5 right-2.5 rounded-full bg-black/50 px-2 py-1 text-[11.5px] font-medium text-white">
                    {activePhoto + 1} / {photos.length}
                  </span>
                )}
              </div>
              {photos.length > 1 && (
                <div className="mt-2.5 flex gap-2 overflow-x-auto">
                  {photos.map((src, i) => (
                    <button
                      key={i}
                      onClick={() => setActivePhoto(i)}
                      aria-label={`Photo ${i + 1} of ${photos.length}`}
                      aria-current={activePhoto === i}
                      className={`h-16 w-16 shrink-0 overflow-hidden rounded-lg bg-box ${
                        activePhoto === i ? 'ring-[1.5px] ring-mark ring-offset-2' : 'opacity-70'
                      }`}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={src} alt="" className="h-full w-full object-cover" />
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Details */}
            <div className="mt-5 lg:mt-0 lg:flex-1">
              <p className="text-[11.5px] font-bold uppercase tracking-wide text-accent-ink">{categoryName}</p>
              <h1 className="mt-0.5 text-lg font-bold text-text lg:text-xl">{product.name}</h1>
              <p className="mt-1"><PriceTag product={product} className="text-[30px]" /></p>

              {!product.inStock ? (
                <p className="mt-1 text-[12.5px] font-bold text-text-mute">Out of stock</p>
              ) : (
                lowStock && (
                  <p className="mt-1 text-[12.5px] font-bold text-danger">Only {product.stockQuantity} left</p>
                )
              )}

              {product.collectInPerson && <CollectBanner from={product.collectFrom} days={product.collectWindowDays} />}

              <p className="mt-3 text-[13px] leading-relaxed text-text-mute">
                {product.description || "This merchant hasn't added a description for this product yet."}
              </p>

              {product.colors.length > 0 && (
                <div className="mt-4">
                  <p className="mb-1.5 text-[12.5px] font-bold text-text">Color</p>
                  <div className="flex gap-2">
                    {product.colors.map((color) => (
                      <button
                        key={color}
                        onClick={() => setSelectedColor(color)}
                        aria-label={`Select color ${color}`}
                        aria-pressed={selectedColor === color}
                        className={`h-8 w-8 rounded-full border-2 ${
                          selectedColor === color ? 'border-mark ring-2 ring-surface ring-inset' : 'border-line'
                        }`}
                        style={{ backgroundColor: color }}
                      />
                    ))}
                  </div>
                </div>
              )}

              {product.sizes.length > 0 && (
                <div className="mt-4">
                  <p className="mb-1.5 text-[12.5px] font-bold text-text">Size</p>
                  <div className="flex flex-wrap gap-1.5">
                    {product.sizes.map((size) => (
                      <button
                        key={size}
                        onClick={() => setSelectedSize(size)}
                        aria-pressed={selectedSize === size}
                        className={`rounded-md border px-3 py-1.5 text-[12.5px] ${
                          selectedSize === size
                            ? 'border-mark font-bold text-accent-ink'
                            : 'border-line text-text-mute'
                        }`}
                      >
                        {size}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {appliedDiscount ? (
                <div className="mt-4 flex items-center gap-2.5 rounded-xl border border-line bg-surface p-2.5">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-panel">
                    <Tag size={14} className="text-accent-ink" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[12.5px] font-bold text-text">{appliedDiscount.code} applied</span>
                    <span className="block truncate text-[12px] text-text-mute">
                      -{formatMoney(appliedDiscount.discountAmount)}
                    </span>
                  </span>
                  <button
                    onClick={handleRemoveDiscount}
                    aria-label="Remove discount code"
                    className="shrink-0 text-text-mute hover:text-danger"
                  >
                    <X size={16} />
                  </button>
                </div>
              ) : (
                <div className="mt-4">
                  <div className="flex items-center gap-2">
                    <input
                      value={discountInput}
                      onChange={(e) => {
                        setDiscountInput(e.target.value);
                        setDiscountError(null);
                      }}
                      onKeyDown={(e) => e.key === 'Enter' && handleApplyDiscount()}
                      placeholder="Discount code"
                      className="min-w-0 flex-1 rounded-xl border border-line bg-surface px-3 py-2 text-base sm:text-[13px] text-text placeholder:text-text-mute"
                    />
                    <button
                      onClick={handleApplyDiscount}
                      disabled={!discountInput.trim() || checkingDiscount}
                      className="shrink-0 rounded-xl border border-line px-3 py-2 text-[13px] font-bold text-text disabled:opacity-50"
                    >
                      {checkingDiscount ? 'Checking…' : 'Apply'}
                    </button>
                  </div>
                  {discountError && <p className="mt-1.5 text-[12px] text-danger">{discountError}</p>}
                </div>
              )}

              <div ref={buyRowRef} className="mt-4 flex gap-2.5">
                <button
                  onClick={handleBuyNow}
                  disabled={justOrdered || buying || !product.inStock}
                  className={`brand-gradient flex-1 rounded-full py-2.5 text-center text-[14px] font-bold text-white ${
                    !product.inStock ? 'opacity-40' : 'disabled:opacity-70'
                  }`}
                >
                  {buyLabel}
                </button>
                <button
                  onClick={handleAddToCart}
                  disabled={justAdded || !product.inStock}
                  className={`flex-1 rounded-full bg-surface py-2.5 text-center text-[14px] font-bold text-text ${
                    !product.inStock ? 'opacity-40' : 'disabled:opacity-70'
                  }`}
                >
                  {justAdded ? 'Added ✓' : 'Add to cart'}
                </button>
              </div>
              <p className="mt-3 text-center text-[12px] text-text-mute lg:text-left">
                Your payment is held safely and only paid to the seller after delivery.
              </p>
            </div>
          </div>

          {/* "Buy this too": sponsored add-ons that go with this product. Its own panel right under the buy area (a
              set to complete), apart from "More like this" below (alternatives to browse), so the two never compete.
              It renders nothing when the server has no add-on that fits. */}
          <SponsoredTwinCard
            productId={product.id}
            productName={product.name}
            variant="product"
            anchor={product.inStock ? { product, color: selectedColor, size: selectedSize, ready: true, onAdd: handleAddToCart } : undefined}
            onSelectProduct={onSelectRelatedProduct}
            onBuyNow={(p, c, s) => onBuyNow(p, c, s)}
            onAddToCart={onAddToCart}
            className="mt-8 rounded-2xl border border-mark/25 bg-surface p-3.5 shadow-[0_0_0_1px_rgba(0,0,0,0.02)]"
          />

          {/* Same banner/category as this product — tapping one swaps
              this whole screen to that product instead of stacking a new
              one, so there's no back-button chain to climb out of. */}
          {relatedProducts.length > 0 && (
            <div className="mt-8 border-t border-line pt-6">
              <h2 className="mb-3 text-[13px] font-bold text-text">More like this</h2>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
                {relatedProducts.map((p) => (
                  <ProductTile key={p.id} product={p} onSelectProduct={onSelectRelatedProduct} />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
      {showBar && product.inStock && (
        <div className="flex gap-2.5 border-t border-line bg-surface px-4 py-2.5 lg:hidden">
          <button
            onClick={handleBuyNow}
            disabled={justOrdered || buying}
            className="brand-gradient flex-1 rounded-full py-3 text-center text-[14px] font-bold text-white disabled:opacity-70"
          >
            {buyLabel}
          </button>
          <button
            onClick={handleAddToCart}
            disabled={justAdded}
            className="flex-1 rounded-full btn-neutral py-3 text-center text-[14px] font-bold disabled:opacity-70"
          >
            {justAdded ? 'Added ✓' : 'Add to cart'}
          </button>
        </div>
      )}
    </div>
  );
}
