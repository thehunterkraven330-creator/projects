'use client';

import { useState } from 'react';

// Lumin's default picture for someone who has not added one, so a person is never a blank circle or a grey silhouette.
// Each person gets their own colour pair, picked from the name (the same name always gives the same colours, on every screen),
// with their first letter on it and a soft diagonal glint across the corner. It is an SVG, so it fills whatever box it is put
// in at any size, and takes the shape of that box (round, or a rounded square).
const PAIRS: [string, string][] = [
  ['#FF2D6F', '#FF6B35'], // brand pink to orange
  ['#7C3AED', '#FF2D6F'], // violet to pink
  ['#0EA5A4', '#7C3AED'], // teal to violet
  ['#F59E0B', '#EF4444'], // amber to red
  ['#2563EB', '#14B8A6'], // blue to teal
  ['#16A34A', '#0EA5A4'], // green to teal
  ['#4F46E5', '#D946EF'], // indigo to magenta
  ['#EA580C', '#CA8A04'], // burnt orange to gold
];

function pairIndex(name: string): number {
  let h = 5381;
  for (let i = 0; i < name.length; i++) h = ((h << 5) + h + name.charCodeAt(i)) | 0;
  return Math.abs(h) % PAIRS.length;
}

export function initialOf(name?: string | null): string {
  const t = (name ?? '').trim();
  // First letter or digit of the name (skips a leading @ or emoji-less punctuation); "L" for Lumin when there is no name.
  const m = t.match(/[\p{L}\p{N}]/u);
  return (m ? m[0] : 'L').toUpperCase();
}

export function GeneratedAvatar({ name }: { name?: string | null }) {
  const idx = pairIndex((name ?? '').trim().toLowerCase());
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
      <polygon points="0,0 62,0 0,62" fill="#fff" fillOpacity="0.16" />
      <text
        x="50"
        y="50"
        textAnchor="middle"
        dominantBaseline="central"
        fontSize="46"
        fontWeight="800"
        fill="#fff"
        style={{ fontFamily: 'inherit' }}
      >
        {initialOf(name)}
      </text>
    </svg>
  );
}

// A person's picture, or their generated one. Sized by `size` (pixels) or by the box it is put in (className, or the parent).
// If the picture fails to load, the generated one shows instead of a broken image.
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
