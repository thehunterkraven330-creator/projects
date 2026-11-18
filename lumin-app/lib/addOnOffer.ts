// The "Added to cart" sheet (components/AddedToCartSheet.tsx) is offered after a shopper's own tap on Add to cart. Adds made
// from an add-on card, or from the sheet itself, must not open it again, so those run inside quietly(); the cart handler in
// app/page.tsx asks isQuiet() at the moment of the call.
let depth = 0;

export function quietly<T>(fn: () => T): T {
  depth += 1;
  try {
    return fn();
  } finally {
    depth -= 1;
  }
}

export const isQuiet = (): boolean => depth > 0;

export const ADDED_EVENT = 'lumin:added-to-cart';
export type AddedDetail = { productId: string; name: string };
