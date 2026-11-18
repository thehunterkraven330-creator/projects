import { Bell, CircleDot, ListVideo, Scan, Search, Settings, ShoppingCart, User } from 'lucide-react';
import { useStoriesTray } from '@/lib/storyTray';
import { BrandLogo } from './BrandLogo';

interface NavBarProps {
  onOpenProfile: () => void;
  onOpenWatchlist: () => void;
  onOpenSettings: () => void;
  onOpenStories: () => void;
  onOpenNotifications: () => void;
  onOpenCart: () => void;
  onOpenSearch: () => void;
  onOpenScan: () => void;
  unreadNotificationCount: number;
  cartCount: number;
}

export function NavBar({
  onOpenProfile,
  onOpenWatchlist,
  onOpenSettings,
  onOpenStories,
  onOpenNotifications,
  onOpenCart,
  onOpenSearch,
  onOpenScan,
  unreadNotificationCount,
  cartCount,
}: NavBarProps) {
  const { unseen } = useStoriesTray();
  return (
    <>
      {/* Left corner: sits only above the category drawer's 220px column. It holds the platform logo. */}
      <div className="fixed left-0 top-0 z-30 hidden h-16 w-[220px] items-center border-b border-r border-line bg-surface px-[18px] lg:flex">
        <BrandLogo className="h-9 max-w-[184px]" />
      </div>

      {/* Right corner: sits only above the product drawer's column, and is the same width as it (340px, 380px on xl; see ProductDrawer).
          Nothing renders above the video column in between — that's what
          lets the video reach the literal top edge of the screen. */}
      <div className="fixed right-0 top-0 z-30 hidden h-16 w-[340px] items-center justify-center gap-2 border-b border-l border-line bg-surface px-2 lg:flex xl:w-[380px]">
        <button
          onClick={onOpenWatchlist}
          aria-label="Watchlist"
          className="flex shrink-0 items-center gap-1 rounded-full bg-panel px-2 py-1 text-[12px] font-medium text-text-mute hover:text-text"
        >
          <ListVideo size={16} />
          Watchlist
        </button>
        <button
          onClick={onOpenStories}
          aria-label={unseen > 0 ? 'Updates, something new' : 'Updates'}
          className={`relative flex shrink-0 items-center gap-1 rounded-full px-2 py-1 text-[12px] font-medium ${unseen > 0 ? 'bg-panel text-text' : 'bg-panel text-text-mute hover:text-text'}`}
        >
          <CircleDot size={16} />
          Updates
          {unseen > 0 && (
            <span className="absolute -right-1 -top-1 flex h-3 w-3" aria-hidden="true">
              <span className="relative inline-flex h-3 w-3 rounded-full border-2 border-surface bg-[#F5334A]" />
            </span>
          )}
        </button>
        <button
          onClick={onOpenScan}
          aria-label="Scan a video to find the product"
          title="Scan a video to find the product"
          className="shrink-0 text-text-mute hover:text-text"
        >
          <Scan size={18} />
        </button>
        <button onClick={onOpenSearch} aria-label="Search" className="shrink-0 text-text-mute hover:text-text">
          <Search size={18} />
        </button>
        <button onClick={onOpenNotifications} aria-label="Notifications" className="relative shrink-0 text-text-mute hover:text-text">
          <Bell size={18} />
          {unreadNotificationCount > 0 && (
            <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-accent px-1 text-[10.5px] font-bold leading-none text-on-accent">
              {unreadNotificationCount}
            </span>
          )}
        </button>
        <button onClick={onOpenProfile} aria-label="Profile" className="shrink-0 text-text-mute hover:text-text">
          <User size={18} />
        </button>
        <button onClick={onOpenSettings} aria-label="Settings" title="Settings" className="shrink-0 text-text-mute hover:text-text">
          <Settings size={18} />
        </button>
        <button onClick={onOpenCart} aria-label="Cart" className="relative shrink-0 text-text-mute hover:text-text">
          <ShoppingCart size={18} />
          {cartCount > 0 && (
            <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-accent px-1 text-[10.5px] font-bold leading-none text-on-accent">
              {cartCount}
            </span>
          )}
        </button>
      </div>
    </>
  );
}
