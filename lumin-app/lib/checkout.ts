// One door to the card form of whichever gateway the backend says is live (it answers /payments/initialize with `provider`).
import type { ApiPaymentInit } from './api';
import { openPaystackCheckout } from './paystack';
import { openStripeCheckout } from './stripe';

// Thrown when the person closes the payment form without paying. Not a failure: screens stay quiet about it.
export class PaymentCancelledError extends Error {
  constructor() {
    super('Payment cancelled');
    this.name = 'PaymentCancelledError';
  }
}
export const isPaymentCancelled = (err: unknown): boolean =>
  err instanceof PaymentCancelledError || (err instanceof Error && err.message === 'Payment cancelled');

export function openCheckout(init: ApiPaymentInit): Promise<void> {
  if (init.provider === 'stripe') {
    if (!init.client_secret) return Promise.reject(new Error('Payment could not be started'));
    return openStripeCheckout({
      publicKey: init.public_key,
      clientSecret: init.client_secret,
      amountSubunit: init.amount_subunit,
      currency: init.currency,
    });
  }
  return openPaystackCheckout({
    publicKey: init.public_key,
    email: init.email,
    amountSubunit: init.amount_subunit,
    currency: init.currency,
    reference: init.reference,
  });
}
