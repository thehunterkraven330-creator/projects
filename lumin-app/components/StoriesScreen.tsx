'use client';

import { useEffect, useState } from 'react';
import { isolate } from '@/lib/isolate';
import { createPortal } from 'react-dom';
import { ChevronLeft, Plus, Radio, Zap } from 'lucide-react';
import { getMe } from '@/lib/api';
import type { ApiStory, ApiStoryGroup, ApiUser } from '@/lib/api';
import { portalTarget } from '@/lib/portal';
import { useStoryActions } from '@/lib/storyActions';
import { STORIES_CHANGED } from '@/lib/storyRings';
import { useStoriesTray } from '@/lib/storyTray';
import { StoryComposer } from './StoryComposer';
import { StoryViewer } from './StoryViewer';
import { UserAvatar } from './UserAvatar';

function ago(iso: string): string {
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return m < 1 ? 'now' : m < 60 ? `${m}m ago` : `${Math.floor(m / 60)}h ago`;
}

// What the person is announcing right now, if anything: a live that hasn't started, or a sale still running.
function announcement(g: ApiStoryGroup): { label: string; live: boolean } | null {
  const now = Date.now();
  for (const s of [...g.stories].reverse()) {
    if (s.kind === 'live' && s.event_at && new Date(s.event_at).getTime() > now - 3600_000) return { label: 'Going live', live: true };
    if (s.kind === 'sale' && s.event_at && new Date(s.event_at).getTime() > now) return { label: 'Flash sale', live: false };
  }
  return null;
}

function newest(g: ApiStoryGroup): ApiStory {
  return g.stories[g.stories.length - 1];
}

// Everyone you follow who has a story up, in one place that isn't the feed: people with something new first, then the rest.
// Tap a person to watch; it carries on to the next person.
export function StoriesScreen({ onClose, leaveRoomForNav = false }: { onClose: () => void; leaveRoomForNav?: boolean }) {
  const { groups, loaded, reload } = useStoriesTray();
  const actions = useStoryActions();
  const [order, setOrder] = useState<ApiStoryGroup[] | null>(null); // the list being played, fixed while watching
  const [start, setStart] = useState(0);
  const [composing, setComposing] = useState(false);
  const [me, setMe] = useState<ApiUser | null>(null);
  useEffect(() => {
    getMe().then(setMe).catch(() => {});
  }, []);

  const target = portalTarget();
  if (!target) return null;
  const mine = groups.find((g) => g.is_me);
  const others = groups.filter((g) => !g.is_me);
  const fresh = others.filter((g) => g.has_unseen);
  const seen = others.filter((g) => !g.has_unseen);

  const play = (list: ApiStoryGroup[], g: ApiStoryGroup) => {
    setOrder(list);
    setStart(list.indexOf(g));
  };
  const playable = [...(mine ? [mine] : []), ...fresh, ...seen];

  // A square card showing the person's latest update, their round picture on it and their name under it, like WhatsApp's but in a grid.
  const row = (g: ApiStoryGroup) => {
    const a = announcement(g);
    const last = newest(g);
    const isNew = g.has_unseen && !g.is_me;
    return (
      <li key={g.author.id} className="relative">
        <button type="button" onClick={() => play(playable, g)} aria-label={`${g.is_me ? 'Your update' : g.author.display_name}${isNew ? ', new' : ''}`} className="block w-full text-left">
          <span className={`relative block aspect-square overflow-hidden rounded-2xl bg-box`}>
            {last.media_type === 'video' ? (
              // eslint-disable-next-line jsx-a11y/media-has-caption
              <video src={`${last.media_url}#t=0.1`} preload="metadata" muted playsInline className="h-full w-full object-cover" />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={last.media_url} alt="" loading="lazy" className="h-full w-full object-cover" />
            )}
            <span className="pointer-events-none absolute inset-x-0 top-0 h-16 bg-gradient-to-b from-black/45 to-transparent" />
            <span className={`absolute left-2 top-2 inline-flex h-10 w-10 rounded-full p-[2px] bg-white/80`}>
              <span className="block h-full w-full overflow-hidden rounded-full border-2 border-black/20 bg-box">
                <UserAvatar url={g.author.avatar_url} name={g.author.display_name} />
              </span>
            </span>
            {a && (
              <span className="brand-scan absolute right-2 top-2 flex items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] font-bold text-white">
                {a.live ? <Radio size={11} aria-hidden="true" /> : <Zap size={11} aria-hidden="true" />}
                {a.label}
              </span>
            )}
          </span>
          <span className="mt-1.5 block truncate text-[13px] font-bold">{g.is_me ? 'Your update' : g.author.display_name}</span>
          <span className="block truncate text-[11.5px] text-text-mute">{ago(last.created_at)}</span>
        </button>
      </li>
    );
  };
  const grid = 'grid grid-cols-2 gap-x-3 gap-y-4 sm:grid-cols-3 lg:grid-cols-4';

  return createPortal(
    <div role="dialog" data-story-layer {...isolate} style={actions?.layersHidden ? { display: 'none' } : undefined} aria-label="Updates" className={`fixed inset-x-0 top-0 z-[75] ${leaveRoomForNav ? 'bottom-[calc(56px+env(safe-area-inset-bottom,0px))] lg:bottom-0' : 'bottom-0'} flex flex-col bg-surface text-text`}>
      <div className="flex shrink-0 items-center gap-2 border-b border-line px-3 pb-2.5 pt-[max(10px,env(safe-area-inset-top))]">
        <button type="button" onClick={onClose} aria-label="Back" className="flex h-9 w-9 items-center justify-center rounded-full bg-panel">
          <ChevronLeft size={20} />
        </button>
        <p className="min-w-0 flex-1 truncate text-[15px] font-extrabold">Updates</p>
        <button type="button" onClick={() => setComposing(true)} className="flex items-center gap-1 rounded-full bg-panel px-3 py-1.5 text-[12.5px] font-bold">
          <Plus size={14} aria-hidden="true" /> Add
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-8">
        <div className="mx-auto w-full max-w-[860px]">
          {!loaded ? (
            <p className="py-10 text-center text-[13px] text-text-mute">Loading…</p>
          ) : (
            <>
              <ul className={`mt-3 ${grid}`}>
                {mine ? (
                  row(mine)
                ) : (
                  <li>
                    {/* Your card is blank until you post */}
                    <button type="button" onClick={() => setComposing(true)} aria-label="Add an update" className="block w-full text-left">
                      <span className="relative flex aspect-square flex-col items-center justify-center gap-1 rounded-2xl border border-dashed border-line bg-panel">
                        <span className="absolute left-2 top-2 inline-flex h-10 w-10 overflow-hidden rounded-full border-2 border-surface bg-box">
                          <UserAvatar url={me?.avatar_url} name={me?.display_name ?? 'You'} />
                        </span>
                        <Plus size={26} strokeWidth={2.5} className="text-accent-ink" aria-hidden="true" />
                        <span className="text-[12px] font-bold">Add update</span>
                      </span>
                      <span className="mt-1.5 block text-[13px] font-bold">Your update</span>
                      <span className="block text-[11.5px] text-text-mute">Gone in 24 hours</span>
                    </button>
                  </li>
                )}
              </ul>
              {fresh.length > 0 && (
                <>
                  <h2 className="mb-1 mt-4 text-[12.5px] font-bold tracking-wide text-text-mute">NEW</h2>
                  <ul className={grid}>{fresh.map(row)}</ul>
                </>
              )}
              {seen.length > 0 && (
                <>
                  <h2 className="mb-1 mt-4 text-[12.5px] font-bold tracking-wide text-text-mute">SEEN</h2>
                  <ul className={grid}>{seen.map(row)}</ul>
                </>
              )}
              {others.length === 0 && <p className="py-6 text-center text-[13px] text-text-mute">None of the people you follow have an update right now. Updates from people you follow show up here for 24 hours, and sellers use them to announce lives and flash sales.</p>}
            </>
          )}
        </div>
      </div>
      {order && (
        <StoryViewer
          back
          hostKeeps
          groups={order}
          startGroup={start}
          onClose={() => {
            setOrder(null);
            reload();
          }}
          onChanged={() => window.dispatchEvent(new Event(STORIES_CHANGED))}
          onLeave={() => {
            setOrder(null);
            onClose();
          }}
          onOpenProduct={(p) => actions?.openProduct(p, { returnHere: true })}
          onAddToCart={(p, c, s) => actions?.addToCart(p, c, s)}
        />
      )}
      {composing && (
        <StoryComposer
          onClose={() => setComposing(false)}
          onPosted={() => {
            setComposing(false);
            reload();
          }}
        />
      )}
    </div>,
    target,
  );
}
