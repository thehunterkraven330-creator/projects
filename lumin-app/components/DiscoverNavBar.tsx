import { ArrowLeft, CircleDot, Scan, Search } from 'lucide-react';
import { useStoriesTray } from '@/lib/storyTray';

interface DiscoverNavBarProps {
  onBack: () => void;
  onOpenSearch: () => void;
  onOpenScan: () => void;
  onOpenStories: () => void;
}

// Desktop-only equivalent of what VideoStage's own overlay already shows
// on mobile/tablet for discover mode (back button, search
// icon) — moved OFF the video card and into a fixed corner instead,
// mirroring NavBar's own left corner treatment for shop mode: fixed
// left-0 top-0, h-16, bordered, lg:flex only, and now the same 220px
// width as CategoryDrawer/NavBar's left corner, since discover carries
// that same column now (see page.tsx). Discover still has no NavBar
// (cart/watchlist/notifications/profile genuinely don't belong here —
// see VideoStage's own comment on that), so this stays deliberately
// smaller: identity + a way back, plus search — all on the left, TikTok-
// sidebar style, rather than split across both top corners the way shop
// splits NavBar's icons left (identity) vs right (actions). No right-
// corner box anymore: search used to live there, and nothing else on
// desktop discover ever did.
export function DiscoverNavBar({ onBack, onOpenSearch, onOpenScan, onOpenStories }: DiscoverNavBarProps) {
  const { unseen } = useStoriesTray();
  return (
    <div className="fixed left-0 top-0 z-30 hidden h-16 w-[220px] items-center gap-3 border-b border-r border-line bg-surface px-[18px] lg:flex">
      <button
        onClick={onBack}
        aria-label="Back to shop"
        className="flex items-center gap-1.5 text-text-mute hover:text-text"
      >
        <ArrowLeft size={18} />
      </button>
      <button
        onClick={onOpenScan}
        aria-label="Scan a video to find the product"
        title="Scan a video to find the product"
        className="ml-auto text-text-mute hover:text-text"
      >
        <Scan size={18} />
      </button>
      <button onClick={onOpenStories} aria-label={unseen > 0 ? 'Updates, something new' : 'Updates'} title="Updates" className="relative text-text-mute hover:text-text">
        <CircleDot size={18} />
        {unseen > 0 && (
          <span className="absolute -right-1 -top-1 flex h-2.5 w-2.5" aria-hidden="true">
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full border-2 border-surface bg-[#F5334A]" />
          </span>
        )}
      </button>
      <button onClick={onOpenSearch} aria-label="Search" className="text-text-mute hover:text-text">
        <Search size={18} />
      </button>
    </div>
  );
}
