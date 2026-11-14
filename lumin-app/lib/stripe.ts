// Stripe's card form (the "Payment Element") in a bottom sheet, for a payment the backend already created via
// /payments/initialize (it hands back a `client_secret`). Card details go straight from this form to Stripe: our server and
// this code never see them. Stripe.js is loaded from js.stripe.com the first time someone pays (Stripe requires that: it must
// not be bundled), and cached after.
//
// Like the old Paystack popup, resolving here is NOT proof of payment (it is just this browser's view): whatever calls it must
// then call /payments/verify with the same reference, which re-checks with Stripe and creates the order.
//
// Built with plain DOM and inline styles (the Tailwind scan only covers app/ and components/), using the app's CSS colour
// variables so it follows light/dark mode.

interface StripeElement {
  mount: (el: HTMLElement) => void;
  unmount: () => void;
  destroy: () => void;
  on?: (event: 'ready' | 'loaderror', cb: (e?: { error?: { message?: string } }) => void) => void;
}
interface StripeInstance {
  elements: (o: { clientSecret: string; appearance?: Record<string, unknown> }) => { create: (t: 'payment') => StripeElement };
  confirmPayment: (o: {
    elements: unknown;
    redirect: 'if_required';
    confirmParams?: Record<string, unknown>;
  }) => Promise<{ error?: { message?: string }; paymentIntent?: { status: string } }>;
}
declare global {
  interface Window {
    Stripe?: (publicKey: string) => StripeInstance;
  }
}

let scriptPromise: Promise<void> | null = null;

function loadStripeScript(): Promise<void> {
  if (typeof window === 'undefined') return Promise.reject(new Error('No window'));
  if (window.Stripe) return Promise.resolve();
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://js.stripe.com/v3/';
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => {
      scriptPromise = null; // let a later tap try again
      reject(new Error('Could not load the payment form. Check your connection and try again.'));
    };
    document.head.appendChild(script);
  });
  return scriptPromise;
}

export interface StripeChargeParams {
  publicKey: string;
  clientSecret: string;
  amountSubunit: number;
  currency: string;
}

const css = (el: HTMLElement, styles: Partial<CSSStyleDeclaration>) => Object.assign(el.style, styles);

export function openStripeCheckout(params: StripeChargeParams): Promise<void> {
  return loadStripeScript().then(
    () =>
      new Promise<void>((resolve, reject) => {
        if (!window.Stripe) {
          reject(new Error('The payment form failed to load'));
          return;
        }
        const stripe = window.Stripe(params.publicKey);
        const dark = document.documentElement.classList.contains('dark');
        const elements = stripe.elements({
          clientSecret: params.clientSecret,
          appearance: { theme: dark ? 'night' : 'stripe', variables: { borderRadius: '10px', colorPrimary: '#E0245E' } },
        });
        const card = elements.create('payment');

        const overlay = document.createElement('div');
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-label', 'Pay');
        css(overlay, { position: 'fixed', inset: '0', zIndex: '100', display: 'flex', alignItems: 'flex-end', justifyContent: 'center', background: 'rgba(0,0,0,0.55)' });

        const sheet = document.createElement('div');
        css(sheet, {
          width: '100%', maxWidth: '480px', maxHeight: '92vh', overflowY: 'auto', boxSizing: 'border-box', padding: '18px 16px calc(22px + env(safe-area-inset-bottom))',
          background: 'rgb(var(--c-surface))', color: 'rgb(var(--c-text))', borderRadius: '24px 24px 0 0',
        });
        sheet.addEventListener('click', (e) => e.stopPropagation());

        const title = document.createElement('p');
        title.textContent = `Pay ${(params.amountSubunit / 100).toFixed(2)} ${params.currency.toUpperCase()}`;
        css(title, { margin: '0 0 12px', fontSize: '17px', fontWeight: '800' });

        const mount = document.createElement('div');
        const error = document.createElement('p');
        css(error, { margin: '10px 0 0', minHeight: '18px', fontSize: '13px', color: 'rgb(var(--c-sale))' });
        error.setAttribute('role', 'alert');

        const pay = document.createElement('button');
        pay.type = 'button';
        const payLabel = `Pay ${params.currency.toUpperCase() === 'USD' ? '$' : ''}${(params.amountSubunit / 100).toFixed(2)}${params.currency.toUpperCase() === 'USD' ? '' : ' ' + params.currency.toUpperCase()}`;
        pay.textContent = payLabel;
        css(pay, {
          width: '100%', marginTop: '12px', padding: '13px', border: '0', borderRadius: '12px', color: 'rgb(var(--c-on-btn))', fontSize: '15px',
          fontWeight: '700', cursor: 'pointer', background: 'rgb(var(--c-btn))',
        });
        const cancel = document.createElement('button');
        cancel.type = 'button';
        cancel.textContent = 'Cancel';
        css(cancel, { width: '100%', marginTop: '6px', padding: '10px', border: '0', background: 'transparent', color: 'rgb(var(--c-mute))', fontSize: '13px', cursor: 'pointer' });

        const safe = document.createElement('p');
        safe.textContent = 'Secure payment by Stripe. Your card details never touch our servers. We hold the money until your order is delivered.';
        css(safe, { margin: '10px 0 0', fontSize: '11.5px', lineHeight: '1.4', textAlign: 'center', color: 'rgb(var(--c-mute))' });

        sheet.append(title, mount, error, pay, safe, cancel);
        overlay.appendChild(sheet);
        document.body.appendChild(overlay);
        card.mount(mount);
        // Wait for the form before allowing a tap on Pay, and say so if it never loads (a bad link or an offline phone).
        pay.disabled = true;
        pay.style.opacity = '0.6';
        card.on?.('ready', () => {
          pay.disabled = false;
          pay.style.opacity = '1';
        });
        card.on?.('loaderror', (e) => {
          error.textContent = e?.error?.message ?? 'The payment form could not load. Close this and try again.';
        });
        const onKey = (ev: KeyboardEvent) => {
          if (ev.key === 'Escape') abort();
        };
        document.addEventListener('keydown', onKey);

        let busy = false;
        const close = () => {
          try {
            card.destroy();
          } catch {
            /* already gone */
          }
          overlay.remove();
          document.removeEventListener('keydown', onKey);
        };
        const abort = () => {
          if (busy) return; // never walk away from a payment that is being confirmed
          close();
          reject(new Error('Payment cancelled'));
        };
        overlay.addEventListener('click', abort);
        cancel.addEventListener('click', abort);

        pay.addEventListener('click', async () => {
          if (busy) return;
          busy = true;
          pay.disabled = true;
          pay.textContent = 'Paying…';
          error.textContent = '';
          try {
            const res = await stripe.confirmPayment({ elements, redirect: 'if_required' });
            if (res.error) {
              error.textContent = res.error.message ?? 'That payment did not go through. Try another card.';
            } else if (res.paymentIntent && ['succeeded', 'processing', 'requires_capture'].includes(res.paymentIntent.status)) {
              close();
              resolve();
              return;
            } else {
              error.textContent = 'That payment did not go through. Try again.';
            }
          } catch {
            error.textContent = 'Could not reach the payment service. Try again.';
          }
          busy = false;
          pay.disabled = false;
          pay.textContent = payLabel;
        });
      }),
  );
}
