// How money is shown. One currency for the whole app: NEXT_PUBLIC_CURRENCY (the same code as the server's PAYMENT_CURRENCY;
// naira launch = NGN). Unset it is USD, which is what every price here used to be hard-coded to.

export const CURRENCY = (process.env.NEXT_PUBLIC_CURRENCY || 'USD').trim().toUpperCase();

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
  const c = (currency ?? '').trim().toUpperCase();
  return /^[A-Z]{3}$/.test(c) ? c : CURRENCY;
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
