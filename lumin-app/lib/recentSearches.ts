// Recent searches, kept on this device only (nothing is sent to the server).
// Every storage call is wrapped: private windows and blocked site data make
// localStorage throw, and search must keep working without it.
export const RECENT_SEARCHES_KEY = 'lumin_recent_searches';
export const RECENT_SEARCHES_MAX = 8;

// Pure: the list after adding `term`. Trimmed, newest first, a repeat (any
// capitalisation) moves to the top instead of appearing twice, capped at MAX.
export function addRecent(list: string[], term: string, max = RECENT_SEARCHES_MAX): string[] {
  const t = term.trim().replace(/\s+/g, ' ');
  if (!t) return list;
  const rest = list.filter((x) => x.toLowerCase() !== t.toLowerCase());
  return [t, ...rest].slice(0, max);
}

export function removeRecent(list: string[], term: string): string[] {
  return list.filter((x) => x !== term);
}

export function loadRecent(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(RECENT_SEARCHES_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed)
      ? parsed.filter((x): x is string => typeof x === 'string').slice(0, RECENT_SEARCHES_MAX)
      : [];
  } catch {
    return [];
  }
}

export function saveRecent(list: string[]): void {
  if (typeof window === 'undefined') return;
  try {
    if (list.length) window.localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(list));
    else window.localStorage.removeItem(RECENT_SEARCHES_KEY);
  } catch {
    /* storage unavailable: the list just isn't remembered */
  }
}
