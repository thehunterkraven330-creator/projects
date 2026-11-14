// How money is shown (a copy of lumin-app/lib/money.ts; keep them the same). NEXT_PUBLIC_CURRENCY (the same code as the server's PAYMENT_CURRENCY;
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

const withCents = make(CURRENCY, 2);
const whole = make(CURRENCY, 0);

// 1500 -> "₦1,500", 1500.5 -> "₦1,500.50", 12 (USD) -> "$12.00". Never throws; anything that is not a number shows as "".
export function formatMoney(n: number): string {
  if (!Number.isFinite(n)) return '';
  return WHOLE_WHEN_POSSIBLE.has(CURRENCY) && Number.isInteger(n) ? whole.format(n) : withCents.format(n);
}

// The same, but "$12" rather than "$12.00" for a whole amount (the compact form used on small cards).
export function formatMoneyShort(n: number): string {
  if (!Number.isFinite(n)) return '';
  return Number.isInteger(n) ? whole.format(n) : withCents.format(n);
}
