'use client';

import { useEffect, useRef, useState } from 'react';
import { BarChart3, ClipboardList, HelpCircle, LayoutGrid, LogOut, MapPin, Tag, Video, Wallet } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { Category, CategoryBanner, MerchantAccount, Order, PickupAddress, Product, VideoPost } from '@/lib/types';
import { MerchantOrders } from './MerchantOrders';
import { MerchantPosts } from './MerchantPosts';
import { MerchantProducts } from './MerchantProducts';
import { MerchantAnalytics } from './MerchantAnalytics';
import { MerchantPayouts } from './MerchantPayouts';
import { MerchantPickupAddress } from './MerchantPickupAddress';
import { SellerVerificationCard } from './SellerVerificationCard';
import { MerchantInsights } from './MerchantInsights';
import { TWIN_ENABLED } from '@/lib/features';
import { formatMoney } from '@/lib/money';

export type MerchantSection = 'overview' | 'products' | 'posts' | 'orders' | 'pickup' | 'payouts' | 'analytics' | 'demand';

const allSections: { id: MerchantSection; label: string; Icon: LucideIcon }[] = [
  { id: 'overview', label: 'Overview', Icon: LayoutGrid },
  { id: 'products', label: 'Products', Icon: Tag },
  { id: 'posts', label: 'Posts', Icon: Video },
  { id: 'demand', label: 'Demand', Icon: HelpCircle },
  { id: 'orders', label: 'Orders', Icon: ClipboardList },
  { id: 'pickup', label: 'Pickup', Icon: MapPin },
  { id: 'payouts', label: 'Payouts', Icon: Wallet },
  { id: 'analytics', label: 'Analytics', Icon: BarChart3 },
];
// Demand (requests you can answer, keyword insights) is part of the twin discovery layer.
const sections = allSections.filter((s) => TWIN_ENABLED || s.id !== 'demand');

function OverviewSection({
  account,
  productsCount,
  postsCount,
  ordersCount,
  revenue,
  onGoToPayouts,
  onGoTo,
}: {
  account: MerchantAccount;
  productsCount: number;
  postsCount: number;
  ordersCount: number;
  revenue: number;
  onGoToPayouts: () => void;
  onGoTo: (section: MerchantSection) => void;
}) {
  // A new seller's first steps, in the order that works: a product, a video about it, then payouts. Disappears once all done.
  const steps: { label: string; hint: string; done: boolean; section: MerchantSection }[] = [
    { label: 'Add your first product', hint: 'Photos, price, sizes and colours', done: productsCount > 0, section: 'products' },
    { label: 'Post a video about it', hint: 'Shoppers buy straight from your videos', done: postsCount > 0, section: 'posts' },
    { label: 'Add your pickup address', hint: 'Where the driver collects your orders', done: !!account.pickupAddress, section: 'pickup' },
    { label: 'Set up payouts', hint: 'So your money has somewhere to go', done: account.payoutReady, section: 'payouts' },
  ];
  const stepsLeft = steps.filter((st) => !st.done).length;
  return (
    <div className="flex flex-1 flex-col px-4 py-5 lg:px-8 lg:py-8">
      <p className="text-[12.5px] font-bold uppercase tracking-wide text-accent-ink">{account.category}</p>
      <h2 className="mt-0.5 text-lg font-bold text-text lg:text-xl">{account.businessName}</h2>
      {account.description && (
        <p className="mt-1.5 max-w-md text-[13.5px] leading-snug text-text-mute">{account.description}</p>
      )}

      {stepsLeft > 0 && (productsCount === 0 || postsCount === 0 || !account.pickupAddress) ? (
        <div className="mt-4 max-w-md rounded-xl border border-line bg-panel p-3">
          <p className="text-[13.5px] font-bold text-text">Get started · {stepsLeft} step{stepsLeft === 1 ? '' : 's'} left</p>
          <ul className="mt-2 flex flex-col gap-1">
            {steps.map((st, i) => (
              <li key={st.label}>
                <button
                  onClick={() => onGoTo(st.section)}
                  className="flex w-full items-center gap-2.5 rounded-lg px-1 py-1.5 text-left"
                >
                  <span
                    className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${
                      st.done ? 'fill-violet' : 'border border-line text-text-mute'
                    }`}
                  >
                    {st.done ? '✓' : i + 1}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className={`block text-[13px] font-bold ${st.done ? 'text-text-mute line-through' : 'text-text'}`}>{st.label}</span>
                    {!st.done && <span className="block text-[12px] text-text-mute">{st.hint}</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        !account.payoutReady && (
          <button
            onClick={onGoToPayouts}
            className="mt-4 max-w-md rounded-xl border border-line bg-panel p-3 text-left shadow-[inset_3px_0_0_rgb(var(--c-mark))]"
          >
            <p className="text-[13.5px] font-bold text-text">Set up payouts</p>
            <p className="mt-0.5 text-[12.5px] text-text-mute">
              Orders are still selling without this, but funds have nowhere to release to until your
              payout account is set up.
            </p>
          </button>
        )
      )}

      <div className="mt-6 grid grid-cols-2 gap-2.5 lg:max-w-lg lg:grid-cols-4">
        {[
          { label: 'Products', value: String(productsCount) },
          { label: 'Posts', value: String(postsCount) },
          { label: 'Orders', value: String(ordersCount) },
          { label: 'Revenue', value: formatMoney(revenue) },
        ].map((stat) => (
          <div key={stat.label} className="rounded-xl border border-line bg-surface p-3.5 text-center">
            <p className="text-[16px] font-bold text-text">{stat.value}</p>
            <p className="text-[11.5px] text-text-mute">{stat.label}</p>
          </div>
        ))}
      </div>

      <p className="mt-6 max-w-md text-[12.5px] text-text-mute">
        Every number here — including the charts in Analytics — comes from what you&apos;ve actually
        listed, posted, and sold. Nothing is sample data.
      </p>
    </div>
  );
}

interface MerchantDashboardProps {
  account: MerchantAccount;
  onSwitchToPersonal: () => void;
  posts: VideoPost[];
  onAddPost: (post: VideoPost) => void | Promise<void>;
  onUpdatePost: (post: VideoPost) => void | Promise<void>;
  onDeletePost: (post: VideoPost) => void;
  onOpenPost: (post: VideoPost) => void;
  orders: Order[];
  onAdvanceOrderStatus: (id: string, status: Order['status']) => void;
  onCancelOrder: (id: string, reason?: string) => void;
  merchantProducts: Product[];
  categories: Category[];
  categoryBanners: CategoryBanner[];
  onAddProduct: (product: Product) => void | Promise<void>;
  onUpdateProduct: (product: Product) => void | Promise<void>;
  onDeleteProduct: (id: string) => void;
  onAddPayout: (bankCode: string, accountNumber: string) => Promise<void>;
  // Stripe reported a different payout-ready state than the app knew: the parent updates the account.
  onPayoutReadyChange?: (ready: boolean) => void;
  // Saves the pickup address; rejects with the server's message so the form can show it.
  onSavePickupAddress: (address: PickupAddress) => Promise<void>;
  // Lets the parent remember which section was open across a trip to the
  // post gallery player and back (this component remounts on return).
  initialSection?: MerchantSection;
  onSectionChange?: (section: MerchantSection) => void;
  // Open this post in the twin editor on arrival (from a "twin hidden" notification).
  openPostId?: string | null;
  onOpenPostHandled?: () => void;
}

// Admin-dashboard shape (sidebar nav, plain content panels) rather than the
// immersive full-bleed video UI the rest of the app uses — a seller
// dashboard is a "get information, take action" surface, not a "watch
// content" one, so it deliberately doesn't try to look like the shop/
// discover player.
export function MerchantDashboard({
  account,
  onSwitchToPersonal,
  posts,
  onAddPost,
  onUpdatePost,
  onDeletePost,
  onOpenPost,
  orders,
  onAdvanceOrderStatus,
  onCancelOrder,
  merchantProducts,
  categories,
  categoryBanners,
  onAddProduct,
  onUpdateProduct,
  onDeleteProduct,
  onAddPayout,
  onPayoutReadyChange,
  onSavePickupAddress,
  initialSection,
  onSectionChange,
  openPostId,
  onOpenPostHandled,
}: MerchantDashboardProps) {
  const [active, setActive] = useState<MerchantSection>(() => {
    // Stripe sends a seller back to /?payouts=done (or refresh) after its onboarding page: land on Payouts.
    if (typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('payouts')) return 'payouts';
    return initialSection && (TWIN_ENABLED || initialSection !== 'demand') ? initialSection : 'overview';
  });
  // The phone tab strip scrolls sideways: bring the selected tab into view so it is never half off-screen.
  const tabStripRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = tabStripRef.current?.querySelector('[aria-current="page"]');
    if (el && 'scrollIntoView' in el) (el as HTMLElement).scrollIntoView({ inline: 'center', block: 'nearest' });
  }, [active]);
  useEffect(() => {
    onSectionChange?.(active);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);
  const revenue = orders.reduce((sum, o) => sum + o.price, 0);

  return (
    <div className="flex h-full flex-col bg-panel lg:flex-row">
      {/* Desktop: real sidebar. */}
      <aside className="hidden w-[240px] shrink-0 flex-col border-r border-line bg-surface lg:flex">
        <div className="border-b border-line px-5 py-5">
          <p className="text-[11.5px] font-bold uppercase tracking-wide text-accent-ink">Business page</p>
          <p className="mt-0.5 truncate text-[14px] font-bold text-text">{account.businessName}</p>
        </div>
        <nav className="flex flex-1 flex-col gap-0.5 px-3 py-3">
          {sections.map(({ id, label, Icon }) => (
            <button
              key={id}
              onClick={() => setActive(id)}
              aria-current={active === id ? 'page' : undefined}
              className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] font-medium ${
                active === id ? 'bg-panel text-accent-ink' : 'text-text-mute hover:bg-panel hover:text-text'
              }`}
            >
              <Icon size={18} />
              {label}
            </button>
          ))}
        </nav>
        <button
          onClick={onSwitchToPersonal}
          className="flex items-center gap-2.5 border-t border-line px-5 py-4 text-left text-[13.5px] font-medium text-text-mute hover:text-text"
        >
          <LogOut size={17} />
          Switch to personal
        </button>
      </aside>

      {/* Mobile/tablet: top bar + horizontally scrollable tab strip instead
          of a sidebar — there's no room for one, and this app doesn't use
          a bottom-nav pattern anywhere else to borrow from. */}
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-surface px-4 lg:hidden">
        <div className="min-w-0">
          <p className="text-[11.5px] font-bold uppercase tracking-wide text-accent-ink">Business page</p>
          <p className="truncate text-[13px] font-bold text-text">{account.businessName}</p>
        </div>
        <button
          onClick={onSwitchToPersonal}
          aria-label="Switch to personal account"
          className="shrink-0 rounded-full border border-line px-3 py-1.5 text-[12.5px] font-bold text-text-mute"
        >
          Switch
        </button>
      </div>
      <div ref={tabStripRef} className="flex shrink-0 gap-2 overflow-x-auto border-b border-line bg-surface px-4 py-2.5 lg:hidden">
        {sections.map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => setActive(id)}
            aria-current={active === id ? 'page' : undefined}
            className={`flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-[12.5px] font-bold ${
              active === id ? 'fill-violet text-white' : 'bg-panel text-text-mute'
            }`}
          >
            <Icon size={15} />
            {label}
          </button>
        ))}
      </div>

      <div className="flex flex-1 flex-col overflow-y-auto">
        {active === 'overview' && (
          <OverviewSection
            account={account}
            productsCount={merchantProducts.length}
            postsCount={posts.length}
            ordersCount={orders.length}
            revenue={revenue}
            onGoToPayouts={() => setActive('payouts')}
            onGoTo={(section) => setActive(section)}
          />
        )}
        {active === 'products' && (
          <MerchantProducts
            products={merchantProducts}
            categories={categories}
            categoryBanners={categoryBanners}
            onAddProduct={onAddProduct}
            onUpdateProduct={onUpdateProduct}
            onDeleteProduct={onDeleteProduct}
          />
        )}
        {active === 'posts' && (
          <MerchantPosts
            posts={posts}
            merchantProducts={merchantProducts}
            onAddPost={onAddPost}
            onUpdatePost={onUpdatePost}
            onDeletePost={onDeletePost}
            onOpenPost={onOpenPost}
            onGoToProducts={() => setActive('products')}
            openPostId={openPostId}
            onOpenPostHandled={onOpenPostHandled}
          />
        )}
        {active === 'demand' && <MerchantInsights />}
        {active === 'pickup' && <MerchantPickupAddress account={account} onSave={onSavePickupAddress} />}
        {active === 'orders' && (
          <>
            {!account.pickupAddress && orders.some((o) => o.status === 'pending') && (
              <button
                onClick={() => setActive('pickup')}
                className="mx-4 mt-4 block max-w-md rounded-xl border border-line bg-panel p-3 text-left shadow-[inset_3px_0_0_rgb(var(--c-mark))] lg:mx-8"
              >
                <p className="text-[13.5px] font-bold text-text">Add your pickup address</p>
                <p className="mt-0.5 text-[12.5px] text-text-mute">
                  You need it before you can seal an order, so the driver knows where to collect it.
                </p>
              </button>
            )}
            <MerchantOrders orders={orders} onAdvanceStatus={onAdvanceOrderStatus} onCancel={onCancelOrder} />
          </>
        )}
        {active === 'analytics' && <MerchantAnalytics orders={orders} posts={posts} />}
        {active === 'payouts' && (
          <>
            <SellerVerificationCard />
            <MerchantPayouts account={account} onSave={onAddPayout} onReadyChange={onPayoutReadyChange} />
          </>
        )}
      </div>
    </div>
  );
}
