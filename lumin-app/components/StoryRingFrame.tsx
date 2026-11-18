'use client';

import type { ReactNode } from 'react';
import { useStoryRing } from '@/lib/storyRings';

// The story ring for a picture that sits inside something already tappable (a search result, a follower row), so it only
// draws the ring: coloured while something is new, grey once it has all been watched, nothing when there is no story.
// The ring is drawn outside the box, so the layout does not move when it appears. Tapping the row opens the profile, where
// the picture itself opens the story.
export function StoryRingFrame({ userId, className = '', children }: { userId?: string; className?: string; children: ReactNode }) {
  const ring = useStoryRing(userId);
  const look = ring.has ? `ring-2 ring-offset-2 ring-offset-surface ${ring.unseen ? 'ring-accent' : 'ring-neutral-400/60'}` : '';
  return <span className={`${className} ${look}`}>{children}</span>;
}
