# First run against Terminal Africa (sandbox)

The Terminal Africa code has never run against the real service. This is the one-time test that proves it, using the sandbox: nothing is
booked, no driver is sent, no money moves. Do it on the STAGING Railway environment, never production. About 30 minutes.

## What you need
- A Terminal Africa account, and its **sandbox** secret key (starts `sk_test_`). Created in Terminal's dashboard; where exactly the key and
  the webhook page are depends on their dashboard, so follow their own docs for that part.
- Staging with **test** payment keys (Paystack test keys for Nigeria, or Stripe test keys for US/UK), so you can pay with a test card.
- Two accounts on staging: a **seller** with a complete pickup address (name, phone, street, city, state, country, postal code) and a
  product in stock, and a **buyer** with a complete delivery address (country from the list, postal code, a real-format phone number).

## 1. Set the variables on the staging backend (Railway > backend > Variables)
| Variable | Value |
|---|---|
| `COURIER` | `terminal` |
| `TERMINAL_AFRICA_SECRET_KEY` | the `sk_test_...` key |
| `TERMINAL_AFRICA_URL` | leave unset (the default is the sandbox) |
| `TERMINAL_CURRENCY` | the currency Terminal quotes in. For a Nigeria-to-Nigeria test use `NGN`, the same as the charge currency, so no conversion rate is needed |

Redeploy. In the deploy log nothing about Terminal should error at start. (Never paste the key in a chat or a file.)

## 2. Check the quote at checkout
1. As the buyer, add the seller's product to the cart and open checkout.
2. The delivery line should show a price that is NOT your flat fee (`SHIPPING_FLAT_FEE_NG`). A live quote is the cheapest rate plus the
   buffer (10% by default).
3. In the backend log look for a line that mentions Terminal. If the price equals the flat fee, the quote was refused and the reason is
   logged ("falls back to the flat fee ... and is logged"). That line is what I need.

## 3. Check the booking
A **test order** (the `TEST_ORDER_FOR` tool) deliberately never books a courier, so it cannot be used here. Use a real checkout with a
test card instead:
1. Pay for the order as the buyer with the provider's test card.
2. As the seller, open the order and do the live test, seal the bag (the sealing step is what asks Terminal to arrange pickup).
3. Success: Admin > Shipments shows the order with a Terminal shipment reference, and the log shows no `TerminalError`.

## 4. Check the status updates (webhook)
1. In Terminal's dashboard add a webhook pointing to `https://<your staging backend>/courier/terminal-webhook` (https only), with the
   shipment events.
2. Trigger or wait for a status change in the sandbox. The backend checks the `X-Terminal-Signature` header with the same secret key.
3. Success: the shipment's status in Admin > Shipments follows Terminal's. A `401` in the log means the signature did not match (wrong key
   on the backend, or the body was altered on the way).

## If something fails: what to send me
For each step that fails, the Railway log lines around it, with the secret key and any card details removed. Most useful of all: the raw
reply Terminal gave. Two parts of the code are guesses and are the likeliest to need a one-line fix:
- `_pick` in `lumin-backend/app/terminal.py`: the names of the id fields in Terminal's replies (shipment id, rate id).
- `_rate_amount`: the name of the price field on a rate.
Also check: whether an item's `weight` is per unit or for the whole line (a heavy order could be priced wrong), and whether Terminal
quotes and delivers for your country pair at all (US and UK are not confirmed).

## Before going live with real drivers
Only after steps 2-4 pass in the sandbox: set `TERMINAL_AFRICA_URL=https://api.terminal.africa/v1`, the **live** key, and register the
webhook again for the live account. Make one real, low-value order first and watch it to delivery.
