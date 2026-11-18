'use client';

import { useCallback, useEffect, useState } from 'react';
import { isolate } from '@/lib/isolate';
import { createPortal } from 'react-dom';
import { ChevronLeft, Eye, Play, Plus } from 'lucide-react';
import { getUserStories, type ApiStory, type ApiStoryGroup } from '@/lib/api';
import { portalTarget } from '@/lib/portal';
import { useStoryActions } from '@/lib/storyActions';
import { STORIES_CHANGED } from '@/lib/storyRings';
import { StoryComposer } from './StoryComposer';
import { StoryViewer } from './StoryViewer';
import { UserAvatar } from './UserAvatar';

interface Props {
  userId: string;
  name: string;
  avatarUrl?: string | null;
  onOpenPicture: () => void; // the profile picture, full screen, as it always opened
  onClose: () => void;
}

function ago(iso: string): string {
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return m < 1 ? 'now' : m < 60 ? `${m}m` : `${Math.floor(m / 60)}h`;
}

// What opens when you tap a profile picture that has a story: a screen with a "Profile picture" section and a "Stories"
// section, each with its own header. Tap the picture to see it full size; tap a story to watch from that one.
export function PersonStoriesScreen({ userId, name, avatarUrl, onOpenPicture, onClose }: Props) {
  const [group, setGroup] = useState<ApiStoryGroup | null | undefined>(undefined); // undefined = loading
  const [playing, setPlaying] = useState<number | null>(null);
  const [composing, setComposing] = useState(false);
  const actions = useStoryActions();

  const load = useCallback(() => {
    getUserStories(userId).then(setGroup).catch(() => setGroup(null));
  }, [userId]);
  useEffect(load, [load]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && playing === null && !composing && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, playing, composing]);

  const target = portalTarget();
  if (!target) return null;
  const stories: ApiStory[] = group?.stories ?? [];
  const isMe = group?.is_me ?? false;
  const newest = [...stories].reverse(); // newest first in the grid; the player still goes oldest to newest

  return createPortal(
    <div role="dialog" data-story-layer {...isolate} aria-label={`${name}: profile picture and updates`} className="fixed inset-0 z-[75] flex flex-col bg-surface text-text">
      <div className="flex shrink-0 items-center gap-2 border-b border-line px-3 pb-2.5 pt-[max(10px,env(safe-area-inset-top))]">
        <button type="button" onClick={onClose} aria-label="Back" className="flex h-9 w-9 items-center justify-center rounded-full bg-panel">
          <ChevronLeft size={20} />
        </button>
        <p className="min-w-0 flex-1 truncate text-[15px] font-extrabold">{name}</p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-8">
        <div className="mx-auto w-full max-w-[560px]">
          <h2 className="mb-2.5 mt-5 text-[13px] font-bold tracking-wide text-text-mute">PROFILE PICTURE</h2>
          <button type="button" onClick={onOpenPicture} aria-label={`View ${name}'s profile picture`} className="mx-auto block h-[168px] w-[168px] overflow-hidden rounded-full bg-box">
            <UserAvatar url={avatarUrl} name={name} />
          </button>
          <p className="mt-2 text-center text-[12px] text-text-mute">Tap to see it full size</p>

          <h2 className="mb-2.5 mt-7 text-[13px] font-bold tracking-wide text-text-mute">UPDATES</h2>
          {group === undefined ? (
            <p className="py-6 text-center text-[13px] text-text-mute">Loading…</p>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-2">
                {isMe && (
                  <button type="button" onClick={() => setComposing(true)} className="flex aspect-[3/4] flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-line bg-panel text-[12px] font-bold text-accent-ink">
                    <Plus size={22} strokeWidth={2.5} aria-hidden="true" />
                    Add update
                  </button>
                )}
                {newest.map((s) => {
                  const index = stories.indexOf(s);
                  const fresh = !s.seen && !isMe;
                  return (
                    <button key={s.id} type="button" onClick={() => setPlaying(index)} aria-label={`Update from ${ago(s.created_at)} ago${fresh ? ', new' : ''}`} className={`relative aspect-[3/4] overflow-hidden rounded-xl bg-box`}>
                      {s.media_type === 'video' ? (
                        // eslint-disable-next-line jsx-a11y/media-has-caption
                        <video src={`${s.media_url}#t=0.1`} preload="metadata" muted playsInline className="h-full w-full object-cover" />
                      ) : (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={s.media_url} alt="" loading="lazy" className="h-full w-full object-cover" />
                      )}
                      {fresh && <span className="absolute right-1.5 top-1.5 h-3 w-3 rounded-full border-2 border-white bg-[#F5334A]" aria-hidden="true" />}
                      <span className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-black/70 to-transparent px-1.5 pb-1 pt-5 text-[11px] font-semibold text-white">
                        <span>{ago(s.created_at)}</span>
                        {isMe ? (
                          <span className="flex items-center gap-0.5">
                            <Eye size={12} aria-hidden="true" />
                            {s.views_count ?? 0}
                          </span>
                        ) : (
                          s.media_type === 'video' && <Play size={12} aria-hidden="true" />
                        )}
                      </span>
                    </button>
                  );
                })}
              </div>
              {stories.length === 0 && !isMe && <p className="py-4 text-center text-[13px] text-text-mute">No updates right now. They last 24 hours.</p>}
            </>
          )}
        </div>
      </div>

      {playing !== null && group && stories.length > 0 && (
        <StoryViewer
          back
          groups={[group]}
          startGroup={0}
          startStory={Math.min(playing, stories.length - 1)}
          onClose={() => {
            setPlaying(null);
            load(); // seen / deleted while watching
          }}
          onChanged={() => window.dispatchEvent(new Event(STORIES_CHANGED))}
          onLeave={() => {
            setPlaying(null);
            onClose();
          }}
          onOpenProduct={(p) => {
            setPlaying(null);
            onClose();
            actions?.openProduct(p);
          }}
          onAddToCart={(p, c, s) => actions?.addToCart(p, c, s)}
        />
      )}
      {composing && (
        <StoryComposer
          onClose={() => setComposing(false)}
          onPosted={() => {
            setComposing(false);
            load();
          }}
        />
      )}
    </div>,
    target,
  );
}
