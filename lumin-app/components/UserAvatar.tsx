'use client';

import { useState } from 'react';

// The default picture for someone who has not added one: a calm, modern person shape (head and shoulders) on a soft colour that
// is picked from the name, so people are easy to tell apart without it looking like a form field or a cartoon. The same name
// always gets the same colour. It is an SVG, so it fills whatever box it is put in and takes that box's shape.
const PAIRS: [string, string][] = [
  ['#FFB59E', '#FF7A8A'],
  ['#C4B5FD', '#8B9CF8'],
  ['#8EE3D0', '#5BB8E8'],
  ['#FFD58A', '#FF9F7A'],
  ['#A5D8FF', '#8FA8FF'],
  ['#9BE7B5', '#5CC9B8'],
  ['#F5B5F0', '#B49CFF'],
  ['#FFC9A0', '#F2A65A'],
];

function hashOf(name: string): number {
  let h = 5381;
  for (let i = 0; i < name.length; i++) h = ((h << 5) + h + name.charCodeAt(i)) | 0;
  return h >>> 0;
}

export function GeneratedAvatar({ name }: { name?: string | null }) {
  const key = (name ?? '').trim().toLowerCase() || 'lumin';
  const idx = hashOf(key) % PAIRS.length;
  const [a, b] = PAIRS[idx];
  const id = `lav${idx}`;
  return (
    <svg viewBox="0 0 100 100" className="block h-full w-full" aria-hidden="true" preserveAspectRatio="xMidYMid slice">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={a} />
          <stop offset="1" stopColor={b} />
        </linearGradient>
      </defs>
      <rect width="100" height="100" fill={`url(#${id})`} />
      <circle cx="50" cy="39" r="17" fill="#FFFFFF" fillOpacity="0.92" />
      <path d="M15 100 C15 76 31 65 50 65 C69 65 85 76 85 100 Z" fill="#FFFFFF" fillOpacity="0.92" />
    </svg>
  );
}

export function UserAvatar({
  url,
  name,
  size,
  className = '',
  shape = 'full',
}: {
  url?: string | null;
  name?: string | null;
  size?: number;
  className?: string;
  shape?: 'full' | 'square';
}) {
  const [broken, setBroken] = useState<string | null>(null);
  const round = shape === 'full' ? 'rounded-full' : 'rounded-2xl';
  const style = size ? { width: size, height: size } : undefined;
  const useImage = !!url && broken !== url;
  return (
    <span
      style={style}
      className={`relative inline-block shrink-0 overflow-hidden bg-box align-middle ${round} ${size ? '' : 'h-full w-full'} ${className}`}
    >
      {useImage ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url as string} alt="" className="block h-full w-full object-cover" onError={() => setBroken(url as string)} />
      ) : (
        <GeneratedAvatar name={name} />
      )}
    </span>
  );
}
