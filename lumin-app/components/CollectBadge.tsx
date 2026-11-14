import { MapPin } from 'lucide-react';

// "Collect in person" is a different way of buying, not a detail of the product, so it gets its own bright badge and
// banner instead of a line of grey text. `pill` is the small badge for lists, cards and the cart; `banner` is the
// block on the product page that explains the three steps.
export function CollectBadge({ from, className = '' }: { from?: string | null; className?: string }) {
  return (
    <span
      className={`inline-flex max-w-full items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-[11px] font-extrabold uppercase tracking-wide text-on-accent ${className}`}
    >
      <MapPin size={12} strokeWidth={2.75} className="shrink-0" aria-hidden />
      <span className="truncate">Collect in person{from ? ` · ${from}` : ''}</span>
    </span>
  );
}

export function CollectBanner({ from, days }: { from?: string | null; days?: number }) {
  const steps = [
    { n: '1', title: 'Pay now', text: 'Your money is held safely. The seller is not paid yet.' },
    { n: '2', title: 'Go and inspect it', text: days ? `You get the seller's address after you pay. Visit within ${days} day${days === 1 ? '' : 's'}.` : "You get the seller's address after you pay." },
    { n: '3', title: 'Accept or reject', text: 'Accept and the seller is paid. Reject and you are refunded in full.' },
  ];
  return (
    <section className="mt-4 overflow-hidden rounded-2xl border-2 border-accent bg-surface" aria-label="Collect in person">
      <div className="flex items-center gap-2.5 bg-accent px-3.5 py-2.5 text-on-accent">
        <MapPin size={22} strokeWidth={2.5} className="shrink-0" aria-hidden />
        <div className="min-w-0">
          <p className="text-[15px] font-extrabold leading-tight">Collect in person{from ? ` from ${from}` : ''}</p>
          <p className="text-[12px] font-semibold leading-tight opacity-80">See it with your own eyes before the seller is paid. No delivery fee.</p>
        </div>
      </div>
      <ol className="grid gap-2.5 px-3.5 py-3 sm:grid-cols-3">
        {steps.map((s) => (
          <li key={s.n} className="flex gap-2.5 sm:flex-col sm:gap-1.5">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-text text-[12px] font-extrabold text-surface">{s.n}</span>
            <span className="min-w-0">
              <span className="block text-[13px] font-extrabold text-text">{s.title}</span>
              <span className="block text-[12px] leading-snug text-text-mute">{s.text}</span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
