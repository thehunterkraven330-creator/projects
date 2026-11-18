'use client';

import { useCallback, useEffect, useState } from 'react';
import { getToken, listExploreStories, listStories, type ApiStoryGroup } from './api';
import { STORIES_CHANGED } from './storyRings';

const REFRESH_MS = 120_000;
const FRESH_MS = 15_000; // the nav button, the menu and the Stories screen all ask: one request serves them

let cache: { at: number; groups: ApiStoryGroup[] } | null = null;
let inflight: Promise<ApiStoryGroup[]> | null = null;

function fetchTray(force: boolean): Promise<ApiStoryGroup[]> {
  if (!force && cache && Date.now() - cache.at < FRESH_MS) return Promise.resolve(cache.groups);
  if (!inflight) {
    inflight = listStories()
      .then((g) => {
        cache = { at: Date.now(), groups: g };
        return g;
      })
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}

// Who has a story up (your own, then people you follow), kept fresh. `unseen` is how many people have something you haven't
// watched, for the dot on the Stories button.
export function useStoriesTray(enabled = true) {
  const [groups, setGroups] = useState<ApiStoryGroup[]>(() => cache?.groups ?? []);
  const [loaded, setLoaded] = useState(!!cache);

  const load = useCallback(
    (force = false) => {
      if (!enabled || !getToken()) return;
      fetchTray(force)
        .then((g) => {
          setGroups(g);
          setLoaded(true);
        })
        .catch(() => setLoaded(true));
    },
    [enabled],
  );

  useEffect(() => {
    if (!enabled) return;
    load();
    const t = setInterval(() => load(), REFRESH_MS);
    const onFocus = () => load();
    const onChanged = () => load(true);
    window.addEventListener('focus', onFocus);
    window.addEventListener(STORIES_CHANGED, onChanged);
    return () => {
      clearInterval(t);
      window.removeEventListener('focus', onFocus);
      window.removeEventListener(STORIES_CHANGED, onChanged);
    };
  }, [enabled, load]);

  const unseen = groups.filter((g) => !g.is_me && g.has_unseen).length;
  return { groups, loaded, unseen, reload: () => load(true) };
}


// Public updates from sellers you don't follow (the Explore list). Shared and cached the same way as the tray.
let exploreCache: { at: number; groups: ApiStoryGroup[] } | null = null;
let exploreInflight: Promise<ApiStoryGroup[]> | null = null;

function fetchExplore(force: boolean): Promise<ApiStoryGroup[]> {
  if (!force && exploreCache && Date.now() - exploreCache.at < FRESH_MS) return Promise.resolve(exploreCache.groups);
  if (!exploreInflight) {
    exploreInflight = listExploreStories()
      .then((g) => {
        exploreCache = { at: Date.now(), groups: g };
        return g;
      })
      .finally(() => {
        exploreInflight = null;
      });
  }
  return exploreInflight;
}

export function useExploreUpdates(enabled = true) {
  const [groups, setGroups] = useState<ApiStoryGroup[]>(() => exploreCache?.groups ?? []);
  useEffect(() => {
    if (!enabled || !getToken()) return;
    const load = (force = false) => fetchExplore(force).then(setGroups).catch(() => {});
    load();
    const t = setInterval(() => load(), REFRESH_MS);
    const onChanged = () => load(true);
    window.addEventListener(STORIES_CHANGED, onChanged);
    return () => {
      clearInterval(t);
      window.removeEventListener(STORIES_CHANGED, onChanged);
    };
  }, [enabled]);
  return groups;
}

// Who the round bubble on the video shows: the first person you follow with something you haven't watched, else the top of the
// Explore list. `count` is how many people have something new there. null when there is nothing to show.
export function useUpdatesBubble(): { who: ApiStoryGroup; count: number } | null {
  const { groups } = useStoriesTray();
  const explore = useExploreUpdates();
  const fresh = groups.filter((g) => !g.is_me && g.has_unseen);
  if (fresh.length > 0) return { who: fresh[0], count: fresh.length };
  const open = explore.filter((g) => g.has_unseen);
  if (open.length > 0) return { who: open[0], count: open.length };
  return null;
}
