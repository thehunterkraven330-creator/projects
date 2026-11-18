// How money is shown. One currency for the whole app: NEXT_PUBLIC_CURRENCY (the same code as the server's PAYMENT_CURRENCY;
// naira launch = NGN). Unset it is USD, which is what every price here used to be hard-coded to.

// The currency each launch country is paid in (the same as the server's app/countries.py).
const COUNTRY_CURRENCY: Record<string, string> = { NG: 'NGN', GH: 'GHS', KE: 'KES', ZA: 'ZAR', US: 'USD', GB: 'GBP', CA: 'CAD', CH: 'CHF' };
const LAUNCH = (process.env.NEXT_PUBLIC_LAUNCH_COUNTRIES ?? '')
  .split(',')
  .map((c) => c.trim().toUpperCase())
  .filter((c) => /^[A-Z]{2}$/.test(c));
// When only one country is open (the naira launch), everyone is charged in its currency, so every amount is shown in it: no
// screen can show a dollar sign by accident, whether or not NEXT_PUBLIC_CURRENCY was set, and whatever a product says.
const SINGLE_COUNTRY_CURRENCY: string | null = LAUNCH.length === 1 ? COUNTRY_CURRENCY[LAUNCH[0]] ?? null : null;

const BUILD_CURRENCY = (SINGLE_COUNTRY_CURRENCY || process.env.NEXT_PUBLIC_CURRENCY || 'USD').trim().toUpperCase();
// The currency the server says buyers are charged in (GET /app-config). The build settings above can fail to reach the deployed web
// app (they are baked in at build time), which left totals in dollars next to naira product prices, so once the server has answered
// its word wins. Until then, and if it never answers, the build setting is used.
let serverCurrency: string | null = null;
let serverSingle = false;
export function setServerCurrency(code: string, singleCountry: boolean): boolean {
  const c = (code ?? '').trim().toUpperCase();
  if (!/^[A-Z]{3}$/.test(c) || (c === serverCurrency && singleCountry === serverSingle)) return false;
  serverCurrency = c;
  serverSingle = singleCountry;
  return true; // changed: screens already drawn should be drawn again
}
// A getter so every use sees the latest value.
export function currentCurrency(): string {
  return serverCurrency ?? BUILD_CURRENCY;
}

// A locale per currency so the symbol is the familiar one (₦, £, R...) rather than the bare code.
const LOCALES: Record<string, string> = {
  NGN: 'en-NG', GHS: 'en-GH', KES: 'en-KE', ZAR: 'en-ZA', USD: 'en-US', GBP: 'en-GB', EUR: 'en-IE', CAD: 'en-CA', AUD: 'en-AU',
};
// Currencies whose prices are normally whole numbers: shown without ".00" when they are.
const WHOLE_WHEN_POSSIBLE = new Set(['NGN', 'KES', 'GHS']);

function make(currency: string, minimumFractionDigits: number): Intl.NumberFormat {
  try {
    return new Intl.NumberFormat(LOCALES[currency] ?? 'en', { style: 'currency', currency, minimumFractionDigits, maximumFractionDigits: 2 });
  } catch {
    return new Intl.NumberFormat('en', { style: 'currency', currency: 'USD', minimumFractionDigits, maximumFractionDigits: 2 });
  }
}

const formatters = new Map<string, { withCents: Intl.NumberFormat; whole: Intl.NumberFormat }>();

function formattersFor(currency: string) {
  let f = formatters.get(currency);
  if (!f) {
    f = { withCents: make(currency, 2), whole: make(currency, 0) };
    formatters.set(currency, f);
  }
  return f;
}

// The currency to show: the one given (a product's own, from the seller's country) when it looks like a code, else the app default.
function pick(currency?: string | null): string {
  if (serverSingle && serverCurrency) return serverCurrency;
  if (SINGLE_COUNTRY_CURRENCY) return currentCurrency();
  const c = (currency ?? '').trim().toUpperCase();
  return /^[A-Z]{3}$/.test(c) ? c : currentCurrency();
}

// 1500 -> "₦1,500", 1500.5 -> "₦1,500.50", 12 (USD) -> "$12.00". Pass a currency (product.currency) when the amount is in one other
// than the app default. Never throws; anything that is not a number shows as "".
export function formatMoney(n: number, currency?: string | null): string {
  if (!Number.isFinite(n)) return '';
  const c = pick(currency);
  const f = formattersFor(c);
  return WHOLE_WHEN_POSSIBLE.has(c) && Number.isInteger(n) ? f.whole.format(n) : f.withCents.format(n);
}

// The same, but "$12" rather than "$12.00" for a whole amount (the compact form used on small cards).
export function formatMoneyShort(n: number, currency?: string | null): string {
  if (!Number.isFinite(n)) return '';
  const f = formattersFor(pick(currency));
  return Number.isInteger(n) ? f.whole.format(n) : f.withCents.format(n);
}
