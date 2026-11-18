'use client';

// Which people have a story to watch right now (the ring around their picture). Asks the server for many people at once,
// remembers the answer for a minute, and asks again after a story is posted, seen or deleted.
import { useEffect, useState } from 'react';
import { getStoryRings, getToken } from './api';

export const STORIES_CHANGED = 'lumin:stories-changed';
type Ring = { has: boolean; unseen: boolean };
const TTL_MS = 60_000;
const NONE: Ring = { has: false, unseen: false };

const cache = new Map<string, { at: number; ring: Ring }>();
const waiting = new Map<string, Array<(r: Ring) => void>>();
let timer: ReturnType<typeof setTimeout> | null = null;

function flush() {
  timer = null;
  const ids = [...waiting.keys()];
  const callbacks = new Map(waiting);
  waiting.clear();
  getStoryRings(ids)
    .then((rows) => {
      const byId = new Map(rows.map((r) => [r.user_id, r]));
      for (const id of ids) {
        const row = byId.get(id);
        const ring: Ring = row ? { has: true, unseen: row.has_unseen } : NONE;
        cache.set(id, { at: Date.now(), ring });
        callbacks.get(id)?.forEach((cb) => cb(ring));
      }
    })
    .catch(() => {
      for (const id of ids) callbacks.get(id)?.forEach((cb) => cb(NONE)); // not cached: asked again next time
    });
}

function ask(id: string, cb: (r: Ring) => void) {
  const hit = cache.get(id);
  if (hit && Date.now() - hit.at < TTL_MS) {
    cb(hit.ring);
    return;
  }
  const list = waiting.get(id) ?? [];
  list.push(cb);
  waiting.set(id, list);
  if (!timer) timer = setTimeout(flush, 60); // one request for everyone shown in the same moment
  if (waiting.size >= 50) {
    if (timer) clearTimeout(timer);
    flush();
  }
}

export function useStoryRing(userId?: string): Ring {
  const [ring, setRing] = useState<Ring>(NONE);
  useEffect(() => {
    if (!userId || !getToken()) {
      setRing(NONE);
      return;
    }
    let live = true;
    const load = () => ask(userId, (r) => live && setRing(r));
    load();
    const onChanged = () => {
      cache.clear();
      load();
    };
    window.addEventListener(STORIES_CHANGED, onChanged);
    return () => {
      live = false;
      window.removeEventListener(STORIES_CHANGED, onChanged);
    };
  }, [userId]);
  return ring;
}
