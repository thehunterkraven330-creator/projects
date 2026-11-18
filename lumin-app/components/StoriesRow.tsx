'use client';

import { useCallback, useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { getToken, listStories, type ApiStoryGroup } from '@/lib/api';
import type { Product } from '@/lib/types';
import { StoryComposer } from './StoryComposer';
import { StoryViewer } from './StoryViewer';
import { STORIES_CHANGED } from '@/lib/storyRings';
import { UserAvatar } from './UserAvatar';

interface Props {
  me: { id: string; name: string; avatar: string | null } | null; // null when logged out: no row
  onOpenProduct: (product: Product) => void;
  onAddToCart: (product: Product, color: string, size: string) => void;
}

export { STORIES_CHANGED } from '@/lib/storyRings';
const REFRESH_MS = 120_000;

// The row of circles above the video on Home: your own story first, then people you follow who have one up (anything new
// first). Tap a circle to watch; tap yours to add one. Stories last 24 hours.
export function StoriesRow({ me, onOpenProduct, onAddToCart }: Props) {
  const [groups, setGroups] = useState<ApiStoryGroup[]>([]);
  const [viewing, setViewing] = useState<number | null>(null);
  const [composing, setComposing] = useState(false);
  const loggedIn = !!me;

  const load = useCallback(() => {
    if (!getToken()) return;
    listStories().then(setGroups).catch(() => {});
  }, []);

  useEffect(() => {
    if (!loggedIn) {
      setGroups([]);
      return;
    }
    load();
    const t = setInterval(load, REFRESH_MS);
    const onFocus = () => load();
    window.addEventListener('focus', onFocus);
    window.addEventListener(STORIES_CHANGED, onFocus);
    return () => {
      clearInterval(t);
      window.removeEventListener('focus', onFocus);
      window.removeEventListener(STORIES_CHANGED, onFocus);
    };
  }, [loggedIn, load]);

  if (!me) return null;
  const mine = groups.findIndex((g) => g.is_me);
  const others = groups.map((g, i) => ({ g, i })).filter((x) => !x.g.is_me);

  return (
    <>
      <div className="shrink-0 border-b border-line bg-surface lg:pr-[296px]">
        <ul className="flex gap-3.5 overflow-x-auto px-3.5 py-2.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" aria-label="Stories">
          <li className="relative w-[58px] shrink-0">
            <button
              type="button"
              onClick={() => (mine >= 0 ? setViewing(mine) : setComposing(true))}
              className="block w-full text-center"
              aria-label={mine >= 0 ? 'View your story' : 'Add to your story'}
            >
              <span className={`mx-auto block h-[54px] w-[54px] rounded-full p-[2.5px] ${mine >= 0 ? 'bg-line' : 'bg-transparent'}`}>
                <UserAvatar url={me.avatar} name={me.name} size={49} className="border-2 border-surface" />
              </span>
              <span className="mt-1 block truncate text-[11px] text-text-mute">Your story</span>
            </button>
            <button
              type="button"
              onClick={() => setComposing(true)}
              aria-label="Add to your story"
              className="brand-gradient absolute right-0 top-[34px] flex h-[22px] w-[22px] items-center justify-center rounded-full border-2 border-surface text-white"
            >
              <Plus size={12} strokeWidth={3} />
            </button>
          </li>
          {others.map(({ g, i }) => (
            <li key={g.author.id} className="w-[58px] shrink-0">
              <button type="button" onClick={() => setViewing(i)} className="block w-full text-center" aria-label={`${g.author.display_name}'s story${g.has_unseen ? ', new' : ''}`}>
                <span className={`mx-auto block h-[54px] w-[54px] rounded-full p-[2.5px] ${g.has_unseen ? 'brand-scan' : 'bg-line'}`}>
                  <UserAvatar url={g.author.avatar_url} name={g.author.display_name} size={49} className="border-2 border-surface" />
                </span>
                <span className={`mt-1 block truncate text-[11px] ${g.has_unseen ? 'font-semibold text-text' : 'text-text-mute'}`}>{g.author.display_name}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      {viewing !== null && groups.length > 0 && (
        <StoryViewer
          groups={groups}
          startGroup={Math.min(viewing, groups.length - 1)}
          onClose={() => setViewing(null)}
          onChanged={load}
          onOpenProduct={onOpenProduct}
          onAddToCart={onAddToCart}
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
    </>
  );
}
