const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// Tells the server about errors that happen in this app, so they show up in the Railway log (and Sentry, when it is on).
// Nothing here may ever cause a problem of its own: every step is wrapped, it sends at most a handful of reports per page load, and
// it never reads or sends anything about the person (no sign-in token, no form contents). The server removes anything that
// looks like a credential before it keeps the message (lumin-backend/app/client_errors.py).
type Kind = 'error' | 'rejection' | 'render';

const MAX_PER_PAGE = 10;
const REPEAT_WINDOW_MS = 60_000;
let sent = 0;
const recent = new Map<string, number>();
let installed = false;

// Not bugs in the app: a lost connection, a request the app cancelled itself, or the browser's own harmless notices.
const IGNORED = [
  /ResizeObserver loop/i,
  /^Script error\.?$/i,
  /Failed to fetch/i,
  /NetworkError/i,
  /Load failed/i,
  /AbortError/i,
  /The user aborted a request/i,
  /Non-Error promise rejection/i,
];

function describe(value: unknown): { message: string; stack?: string } {
  if (value instanceof Error) return { message: `${value.name}: ${value.message}`, stack: value.stack };
  if (typeof value === 'string') return { message: value };
  try {
    return { message: JSON.stringify(value) ?? String(value) };
  } catch {
    return { message: String(value) };
  }
}

export function reportError(kind: Kind, value: unknown): void {
  try {
    if (typeof window === 'undefined' || sent >= MAX_PER_PAGE) return;
    const { message, stack } = describe(value);
    if (!message || IGNORED.some((re) => re.test(message))) return;
    const now = Date.now();
    const last = recent.get(message);
    if (last !== undefined && now - last < REPEAT_WINDOW_MS) return; // the same error over and over is one report
    recent.set(message, now);
    sent += 1;
    fetch(`${API_BASE_URL}/client-errors`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      keepalive: true,
      body: JSON.stringify({
        source: 'admin',
        kind,
        message: message.slice(0, 1500),
        stack: stack?.slice(0, 10000),
        path: window.location.pathname, // path only: never the query string or fragment
      }),
    }).catch(() => {
      /* best effort: a report that cannot be sent is not worth a second error */
    });
  } catch {
    /* never throw from the error reporter */
  }
}

// Once per page: the browser's two catch-all events for errors nothing else handled.
export function installErrorReporting(): void {
  if (installed || typeof window === 'undefined') return;
  installed = true;
  window.addEventListener('error', (e) => reportError('error', e.error ?? e.message));
  window.addEventListener('unhandledrejection', (e) => reportError('rejection', e.reason));
}
