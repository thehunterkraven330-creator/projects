'use client';

import { useState, type ReactNode } from 'react';
import { useStoryRing } from '@/lib/storyRings';
import { PersonStoriesScreen } from './PersonStoriesScreen';
import { UserAvatar } from './UserAvatar';

interface Props {
  userId?: string;
  name: string;
  avatarUrl?: string | null;
  onOpenPicture: () => void; // look at the profile picture, as it always did
  label?: string;
  className?: string; // the size of the round picture, e.g. "h-9 w-9"
  children?: ReactNode; // anything laid over the picture (e.g. an upload spinner)
}

// A round profile picture. With a story it gets a ring (coloured while something is new, grey once all is seen) and a tap
// offers "View story" or "View profile picture"; with no story a tap opens the picture directly, as before.
export function PosterAvatarButton({ userId, name, avatarUrl, onOpenPicture, label, className = 'h-9 w-9', children }: Props) {
  const ring = useStoryRing(userId);
  const [open, setOpen] = useState(false);
  return (
    <>
      <span
        className={`relative inline-flex shrink-0 rounded-full ${className.includes('h-full') ? 'h-full w-full' : ''} ${ring.has ? `p-[2.5px] ${ring.unseen ? 'brand-scan' : 'bg-neutral-400/60'}` : ''}`}
      >
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            if (ring.has) setOpen(true);
            else onOpenPicture();
          }}
          aria-label={ring.has ? `${name}: view updates or profile picture` : label ?? `View ${name}'s profile picture`}
          className={`${className} shrink-0 overflow-hidden rounded-full bg-box ${ring.has ? 'border-2 border-surface' : ''}`}
        >
          <UserAvatar url={avatarUrl} name={name} />
        </button>
        {children}
      </span>
      {open && userId && (
        <PersonStoriesScreen
          userId={userId}
          name={name}
          avatarUrl={avatarUrl}
          onClose={() => setOpen(false)}
          onOpenPicture={() => {
            setOpen(false);
            onOpenPicture();
          }}
        />
      )}
    </>
  );
}
