/**
 * Formats large counts compactly: 999 -> "999", 1000 -> "1k", 4500 -> "4.5k", 999950 -> "1M", 2500000 -> "2.5M".
 * One decimal at most, never a trailing ".0", and a value that rounds up to the next unit moves up to it (so it
 * can't read "1000k"). Anything that isn't a positive number reads "0".
 */
export function formatCount(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return '0';
  const whole = Math.floor(n);
  if (whole < 1000) return `${whole}`;
  const units: [number, string][] = [
    [1e9, 'B'],
    [1e6, 'M'],
    [1e3, 'k'],
  ];
  const at = units.findIndex(([size]) => whole >= size);
  let [size, suffix] = units[at];
  let rounded = Math.round((whole / size) * 10) / 10;
  // Rounded up to 1000 of this unit (999,950 as thousands): say it in the next unit up instead of "1000k".
  if (rounded >= 1000 && at > 0) {
    [size, suffix] = units[at - 1];
    rounded = Math.round((whole / size) * 10) / 10;
  }
  return `${rounded}${suffix}`;
}

/**
 * Formats an ISO timestamp (e.g. VideoPost.created_at from the API) as
 * the same short relative style the seed/mock data already uses by hand
 * — "3h ago", "1d ago" — so a live post reads identically to a seeded
 * one. Falls back to a plain date past a week old rather than counting
 * weeks/months, since nothing in this app's mock data ever needed that.
 */
export function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));

  if (seconds < 60) return 'Just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
