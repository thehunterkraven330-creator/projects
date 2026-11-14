'use client';

import type { ReactNode } from 'react';
import { Bell, CornerUpLeft, Heart, MessageCircle, Package, Repeat2, Smile, Tag, UserPlus } from 'lucide-react';
import type { Notification } from '@/lib/types';
import { PageHeader } from './PageHeader';
import { UserAvatar } from './UserAvatar';

// One glyph and one short label per kind of notice. Same Heart / MessageCircle vocabulary the rest of the app uses
// for like and comment; product (Tag), order (Package), person (UserPlus) and twin (Repeat2) join them, and anything
// untyped (a moderation notice, say) gets a Bell.
function kindOf(n: Notification, size: number): { glyph: ReactNode; label: string } {
  switch (n.type) {
    case 'post_like':
      return { glyph: <Heart size={size} fill="currentColor" />, label: 'Like' };
    case 'post_comment':
      return { glyph: <MessageCircle size={size} />, label: 'Comment' };
    case 'comment_reply':
      return { glyph: <CornerUpLeft size={size} />, label: 'Reply' };
    case 'comment_reaction':
      return { glyph: <Smile size={size} />, label: 'Reaction' };
    case 'retwin':
      return { glyph: <Repeat2 size={size} />, label: 'Retwin' };
    case 'twin_request':
    case 'twin_reply':
    case 'twin_offered':
    case 'twin_flagged':
      return { glyph: <Repeat2 size={size} />, label: 'Twin' };
    case 'product':
      return { glyph: <Tag size={size} />, label: 'Product' };
    case 'order':
      return { glyph: <Package size={size} />, label: n.audience === 'seller' ? 'Business order' : 'Your order' };
    case 'user':
      return { glyph: <UserPlus size={size} />, label: 'People' };
    default:
      return { glyph: <Bell size={size} />, label: 'Notice' };
  }
}

// The person's picture as a rounded square (not a circle), or their first letter when they have none. Notices nobody
// caused show the kind's glyph on a tinted square instead.
function Tile({ n }: { n: Notification }) {
  if (n.actorName) {
    return (
      <span className="block h-14 w-14 shrink-0">
        <UserAvatar url={n.actorAvatarUrl} name={n.actorName} shape="square" />
      </span>
    );
  }
  return (
    <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-box text-text">{kindOf(n, 22).glyph}</span>
  );
}

// The notice text. The person's name is the same weight as the rest of the sentence (it is not bolded or underlined);
// their picture next to it already says who it is.
function BodyWithName({ body }: { body: string; name?: string }) {
  return <>{body}</>;
}

interface NotificationsScreenProps {
  notifications: Notification[];
  onBack: () => void;
  onMarkRead: (id: string) => void;
  onMarkAllRead: () => void;
  onSelectNotification: (notification: Notification) => void;
}

export function NotificationsScreen({
  notifications,
  onBack,
  onMarkRead,
  onMarkAllRead,
  onSelectNotification,
}: NotificationsScreenProps) {
  const unread = notifications.filter((n) => !n.read);
  const earlier = notifications.filter((n) => n.read);

  const handleTap = (n: Notification) => {
    onMarkRead(n.id);
    onSelectNotification(n);
  };

  const row = (n: Notification) => {
    const kind = kindOf(n, 11);
    return (
      <button
        key={n.id}
        onClick={() => handleTap(n)}
        className={`flex w-full items-start gap-3.5 rounded-2xl p-3 text-left transition-colors ${
          n.read ? 'bg-surface hover:bg-panel' : 'bg-panel'
        }`}
      >
        <Tile n={n} />
        <span className="min-w-0 flex-1">
          {/* Top line: the kind of notice as a pill, and when it happened on the right. Nothing is positioned off the
              edge of anything, so long labels like "Business order" can never end up out of place. */}
          <span className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-[3px] text-[9.5px] font-extrabold uppercase tracking-wider ${
                n.read ? 'bg-ink text-white' : 'bg-accent text-on-accent'
              }`}
            >
              {kind.glyph}
              {kind.label}
            </span>
            <span className="ml-auto shrink-0 text-[11.5px] font-medium tabular-nums text-text-mute">{n.time}</span>
          </span>
          <span className="mt-1.5 block text-[14.5px] leading-snug text-text">
            <BodyWithName body={n.body} name={n.actorName} />
          </span>
        </span>
      </button>
    );
  };

  const heading = (text: string, action?: ReactNode) => (
    <div className="mb-2 mt-1 flex items-center justify-between px-1">
      <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-text-mute">{text}</p>
      {action}
    </div>
  );

  return (
    <div className="flex h-full flex-col bg-surface">
      <PageHeader title="Notifications" onBack={onBack} backLabel="Back to shop" />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-lg px-4 py-4 lg:px-0 lg:py-6">
          {notifications.length === 0 ? (
            <div className="flex flex-col items-center gap-1.5 py-16 text-center">
              <Bell size={22} className="text-text-mute" />
              <p className="text-[13px] font-bold text-text">No notifications</p>
              <p className="max-w-[220px] text-[13.5px] text-text-mute">
                You&apos;ll see updates about your orders and wishlist here.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              {unread.length > 0 &&
                heading(
                  `New · ${unread.length}`,
                  <button onClick={onMarkAllRead} className="text-[12px] font-bold text-accent-ink">
                    Mark all as read
                  </button>,
                )}
              {unread.map(row)}
              {earlier.length > 0 && (
                <div className={unread.length > 0 ? 'mt-4' : ''}>{heading(unread.length > 0 ? 'Earlier' : 'All caught up')}</div>
              )}
              {earlier.map(row)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
