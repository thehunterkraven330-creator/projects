# Launch checklist

Written at feature freeze. Everything below is what still has to happen on a real machine: the build sandbox could not
reach npm or PyPI, so nothing was compiled by the real toolchain or run against a database.

## What was checked without the real toolchain
- Frontend (125 files in `lumin-app`, `lumin-admin`): type-checked against stub library types. No errors in our own code.
  (React/Next/lucide types were stubs, so this catches wrong props, wrong field names and wrong types in OUR code,
  not library misuse.)
- Backend: every `.py` file compiles; no undefined names; every `from app.x import y` points at something that exists.
- Migrations: one linear chain `0001` to `0050`, one head, no missing parents. The new ones (0041-0045) are safe to run on
  a fresh database (the baseline already builds the tables) and on an existing one.
- Frontend calls vs backend routes: every `request()` in both apps matches a real route and HTTP method.
- Logic tests that run without a database: 44 pass (sponsored ranking, claim review, seals, shipments, fraud signals).
  The PDF print-sheet test needs `reportlab` installed and was not run.
- Security read of the new routes: constant-time compares for the courier key and the OTP, rate limits on scan/OTP/test
  routes, admin routes behind the admin dependency.

## Do first (in this order)
1. Deploy backend. Watch the log for `Applying migrations...` finishing at `0050_payment_provider`.
   If a migration fails, STOP and send me the error. Do not edit the database by hand.
2. `pip install -r requirements.txt` picks up `reportlab`, `stripe` and `phonenumbers`; the frontend `npm install` picks up `jsqr`.
3. Deploy `lumin-app` and `lumin-admin`. Fix whatever the first real `next build` reports (the earlier two build errors
   were one type error and one apostrophe; expect a few more at most).
4. Run `python -m pytest` in `lumin-backend` (this is the first run of the database tests).

## Settings (Railway variables)
Already required: `DATABASE_URL`, `JWT_SECRET_KEY`, `R2_*` (5 values), `STRIPE_SECRET_KEY`, `STRIPE_PUBLIC_KEY`, `STRIPE_WEBHOOK_SECRET`, `RESEND_API_KEY`, `EMAIL_FROM`,
`FRONTEND_URL`, `CORS_ORIGINS`.

New or newly relevant:

| Variable | Default | Say |
|---|---|---|
| `LAUNCH_COUNTRIES` | NG,US,GB | Countries switched on (see "Several countries" below). The app refuses to boot unless every provider those countries use has its keys. |
| `PAYMENT_PROVIDER` / `PAYMENT_CURRENCY` | stripe / USD | Only the fallback for payments and sellers made before countries decided this. New orders use the country's provider and currency. |
| `SPONSORED_SALE_PERCENT` | 10 | Your cut on add-on sales. Set 20 if you want 20. |
| `SEED_SPONSORED_DEMO` | on | Adds 3 fake demo sellers + 17 products on every deploy. Set `false` before real launch, then `python -m app.seed --remove-sponsored-demo`. |
| `NEXT_PUBLIC_USE_SAMPLE_DATA` (app) | unset | Leave UNSET in production. `true` makes the app show built-in sample videos/products when the server cannot be reached (only for working on the app with no server). |
| `SEAL_REQUIRED_TO_SHIP` | false | Keep false (sealed delivery stays optional). |
| `AUTO_REFUND_CLEAR_CASES` | false | Keep false until you have seen real disputes. |
| `CLAIM_WINDOW_HOURS` / `APPEAL_WINDOW_HOURS` | 48 / 48 | |
| `SEAL_MIN_TEST_SECONDS` | 20 | Shortest accepted live test. |
| `R2_PRIVATE_BUCKET_NAME` | empty | Set it so live-test videos are not public. Needs CORS on the bucket for browser upload. |
| `COURIER` / `COURIER_API_KEY` | manual / empty | `manual`: Admin > Shipments acts as the courier. `terminal`: Terminal Africa books the driver and prices delivery live (below). |
| `TERMINAL_AFRICA_SECRET_KEY` | empty | Terminal's secret key (`sk_test_...` for the sandbox). Railway only, never in code or chat. |
| `TERMINAL_AFRICA_URL` | `https://sandbox.terminal.africa/v1` | The SANDBOX unless you set `https://api.terminal.africa/v1`. |
| `TERMINAL_CURRENCY` | NGN | Currency Terminal quotes in (only used if a rate does not say). |
| `TERMINAL_FX_NGN_USD` | empty | How many checkout-currency units one NGN is worth (name is `TERMINAL_FX_<TERMINAL CURRENCY>_<CHECKOUT CURRENCY>`). Without it a live price is refused and checkout uses the flat fee. Update it when the rate moves. |
| `SHIPPING_QUOTE_BUFFER_PERCENT` | 10 | Added to every live delivery price so a small rate change is not a loss. |
| `DEFAULT_WEIGHT_GRAMS` | 500 | Used for products listed before weight was asked for. |
| `ANTHROPIC_API_KEY` | empty | Optional: AI reads products for better add-on matching. |
| `SENTRY_DSN` | empty | Strongly recommended for the first weeks. |
| `RISK_*` | see `fraud_signals.py` | Warning thresholds for the reviewer; they never block anyone. |

## Stripe checks (TEST mode, before any live key)
Never run against live keys until all of these pass in test mode. None of this has been run against Stripe yet.
1. Stripe dashboard: enable **Connect** (Express), and add the webhook endpoint from `DEPLOY.md`.
2. Seller: Dashboard > Payouts > **Set up with Stripe**. Use Stripe's test onboarding data. Back in the app it should say "Payouts are set up".
3. Buyer: buy with test card `4242 4242 4242 4242`. The order appears; the payment shows in Stripe.
4. Try the failing cards (`4000 0000 0000 9995` declined; `4000 0025 0000 3155` asks for 3-D Secure). No order must be created on a failure.
5. Mark the order delivered, wait out or skip the claim window, release. In Stripe a **transfer** to the seller's account appears, for the price minus any add-on fee.
6. Cancel another order and file a defect claim on a third: each shows a **refund** in Stripe for only that order's amount.
7. Stop the browser mid-payment (close the tab after paying): the webhook should still create the order.

## Real-phone tests before inviting sellers (about 30 minutes)
Use one iPhone (Safari) and one Android (Chrome). Safari is the riskiest.
1. Admin > Seals: make a batch of 5 bags, download the PDF, print one label, scan it with a phone.
2. Seller: place a test order, tap **Go live test**, allow the camera, record 25 seconds, finish. Check the video plays in Admin.
3. Buyer: open the order, scan the bag QR at the door, enter the OTP. Order becomes delivered.
4. Buyer: file a complaint. Check the dispute shows the seller video and the suggestion (deny / refund / review).
5. Repeat step 4 on an order with NO live test: suggestion should be refund.
6. Add-ons: open a product tile, check "Complete your set" / "Frequently bought with" appears, tap "+", add the whole set,
   open the cart and check "Recommended add-on". Check the Terms and Help pages show the add-on commission line.
7. Cancel an order after the live test: the bag should be freed.

## How payouts and disputes now behave
- Sellers are paid by a scheduled sweep every 30 minutes (inside the job loop), not only when someone opens their orders.
  It needs the background jobs to be running (the default, `RUN_JOBS_IN_WEB=true`, or a worker service).
- After an admin DENIES a claim the money stays held until the buyer's appeal window ends (`APPEAL_WINDOW_HOURS`, 48 by
  default), and while an appeal is open. So a seller can wait up to two more days after a denied claim. This is on purpose:
  paying earlier would leave nothing to refund if the buyer wins the appeal.

## Known gaps (accepted for launch)
- (First-run steps: TERMINAL_SANDBOX_TEST.md.) Terminal Africa is written but NEVER RUN against the real service (the build sandbox cannot reach it). Set `COURIER=terminal`, the key and a conversion rate on STAGING first, with the sandbox key, and do one full order: checkout (the delivery price should be a live one, not the flat fee), seal, and check the shipment appears in the Terminal dashboard. Three things were read from their Postman export but never seen answered, so they are the first suspects if it fails: the name of the id field in a shipment response (`shipment_id`), the name of the amount field in a rate (`amount`), and whether an item's `weight` means one unit or the whole line (we send one unit's weight in kg). All three are read in one place, `app/terminal.py` (`_pick`, `_rate_amount`, `parcel_payload`).
- How delivery is priced with `COURIER=terminal`: one live quote per unit (each unit is its own sealed bag and shipment), from the seller's pickup address to the buyer's, cheapest rate, converted to the checkout currency, plus the buffer. When the real booking is made (the seller seals the bag) the cheapest rate then is booked; Lumin absorbs any difference. If anything stops a live price (Terminal down, no conversion rate, seller without a pickup address, a bad address) checkout uses the flat fee and logs a warning, so a courier outage never stops sales. Watch the log for `shipping: no live rate`.
- Delivery addresses are stricter now: a two-letter country (chosen from a list), a postal code, and a phone number that is real for that country (saved as `+234...`). With `COURIER=terminal`, a buyer whose saved address predates this is asked to update it before paying. Sellers need a weight (grams) on every product; the form asks for it. Sellers who saved a pickup address without a postal code are asked again.
- Terminal webhooks: `POST /courier/terminal-webhook`. In Terminal's dashboard (or `POST /webhooks`) register `https://<your backend>/courier/terminal-webhook` with events `shipment.in-transit`, `shipment.cancelled` and `shipment.delivered` (live webhooks must be https). Every request is checked against `X-Terminal-Signature` (hex HMAC-SHA512 of the raw body, keyed with the same secret key) and refused otherwise. `shipment.in-transit` = the driver collected the bag (the buyer is told it is on its way); `shipment.cancelled` = the seller is told and the log shows `Terminal cancelled the pickup` (someone must request another driver); `shipment.delivered` is only logged, it does NOT deliver the order: the buyer's code read to the driver is still the proof. A repeated event does nothing. Test it with Terminal's sandbox `POST /webhooks/simulate` before trusting it: the body layout (`event`, `data.shipment`) and the signature rule were taken from a summary of their docs, not seen live.
- Cancelling an order that is waiting for a driver also cancels the booking at Terminal (so no driver is sent). If Terminal cannot be reached at that moment the order is still cancelled and the buyer still refunded, and the log shows `NOT cancelled at Terminal` with the shipment id: cancel that one by hand in Terminal's dashboard. Check the log for that line during the first weeks.
- Not built: address validation (their paid `/addresses/validate`), customs/HS codes for international parcels, and paying sellers by Paystack in Africa (still one payment provider for the whole app).
- No bundle discount; "Add the whole set" adds items to the cart, it is not a one-payment bundle.
- A seller who wins an appeal after a refund cannot claw the money back automatically (manual compensation).
- Terms/Help wording on add-ons and sealed delivery is plain language, not lawyer-reviewed.

## Scan and the twin switch (read before deciding what to launch with)
- Scanning a video is NOT behind the twin switch. The Scan buttons and the `/scan/*` routes are always on, and the whole scan path (match, result, products, sponsored add-ons) was checked to call nothing that `TWIN_ENABLED` hides. `TWIN_ENABLED` / `NEXT_PUBLIC_TWIN_ENABLED` only control twin search, the Wanted board, the creator twins inbox and impact page, timeline pins and the merchant Demand tab. (Older notes said scan was part of that switch; they were wrong and are corrected.) There is no off switch for scanning itself; say so if you want one.
- After a scan the result lists the products in the video, and the ones on screen during the recording come first, marked "In your recording" (from where the recording started and how long it ran, against each product's twin times). Only shown when some products were in the clip and some were not; a video with no twin timings looks as before.
- Not yet run on real videos: the matching itself (`scan_fp.py`) needs real recordings from real phones to judge. Before launch, scan 10 to 20 recordings of your own test videos, on different phones, and note which are missed.

## Several countries: how payments work now (read this first)
Each country has one payment provider and one currency, set in `lumin-backend/app/countries.py`. The seller's country (their pickup address) decides how they are paid; the order's delivery country picks the gateway and currency a buyer is charged in. An order must be domestic (every seller collects from the country it is delivered to), so one gateway takes the money and the same one pays the seller. The gateway and currency are stored on every payment (migration 0050); refunds, verification and payouts always use the one stored.

| Country | Provider | Currency | State |
| --- | --- | --- | --- |
| Nigeria | Paystack | NGN | Wave 1, on by default |
| United States, United Kingdom | Stripe Connect | USD, GBP | Wave 1, on by default |
| Ghana, Kenya, South Africa | Paystack | GHS, KES, ZAR | Listed, NOT verified: payouts in the code are naira-only |
| Canada, Switzerland, AT BE DE ES FI FR IE IT NL PT | Stripe Connect | CAD, CHF, EUR | Listed, not run against a live platform account |

`LAUNCH_COUNTRIES` (unset = `NG,US,GB`) switches countries on. A country marked "not verified" is refused at startup unless `ALLOW_UNVERIFIED_ROUTES=true`: check it in the provider's test mode first. Set the same list in the websites as `NEXT_PUBLIC_LAUNCH_COUNTRIES`.

**Set up (backend)**: `STRIPE_SECRET_KEY`, `STRIPE_PUBLIC_KEY`, `STRIPE_WEBHOOK_SECRET` (US/UK), `PAYSTACK_SECRET_KEY`, `PAYSTACK_PUBLIC_KEY` (Nigeria). Both webhooks run at once: `/payments/stripe-webhook` and `/payments/webhook`. Set a flat delivery price per country, because the plain one is in one currency: `SHIPPING_FLAT_FEE_NG=2500`, `SHIPPING_FLAT_FEE_US=5`, `FREE_SHIPPING_THRESHOLD_US=50` (the plain `SHIPPING_FLAT_FEE` and `FREE_SHIPPING_THRESHOLD` are the fallback).
**Sellers**: a seller must save a pickup address (in a country that is on) before payout setup: Nigerian sellers add a bank account, US/UK sellers go through Stripe's onboarding. Payout setup before an address is refused.
**Stripe, outside the US**: the platform is a US company paying sellers in other Stripe regions with Stripe's cross-border payouts (US, UK, EEA, Canada, Switzerland only). Countries beyond those need Stripe Global Payouts, which is not built; whether it works with holding money in escrow is a question for Stripe.

**What is NOT built yet (be honest with sellers and buyers)**
- Feeds and search do not filter by the viewer's country. A buyer in one country can see a product from another; checkout then refuses it with a clear message. Products carry a `currency` field and prices on cards show it, but pages other than the price tag still show prices in the app's default currency (`NEXT_PUBLIC_CURRENCY`). Do the filter and the remaining price screens before opening a second country to the public.
- Cross-border orders, mixed-currency carts, converting a price to the buyer's currency, customs.
- Shipping outside Terminal Africa's coverage (not confirmed from its docs): US and UK sellers need another courier; until then use manual shipping with a tracking number.
- Paystack payouts in cedi, shilling and rand; Stripe Global Payouts; an admin screen for stuck payouts.
- None of this has run against live Stripe or Paystack accounts, a database, or a browser build: only the pure parts were tested here. Run the whole backend test suite and use both providers' TEST keys on staging first.

## Nigeria on Paystack: payments, step by step
This is the Paystack side of the table above (Nigeria, naira, domestic). Stripe cannot pay Nigerian sellers, so Nigeria is always Paystack. Nothing below has been run against the real Paystack: use the Paystack TEST keys on staging first.

**Settings (backend)**: `PAYSTACK_SECRET_KEY`, `PAYSTACK_PUBLIC_KEY`, `LAUNCH_COUNTRIES` including `NG`, `SHIPPING_FLAT_FEE_NG` (for example 2500) and `FREE_SHIPPING_THRESHOLD` (0 = no free delivery, or an amount in naira). The server refuses to start with a Paystack country other than Nigeria unless `ALLOW_UNVERIFIED_ROUTES=true` (otherwise a cedi order would pay a seller the same number in naira).
**Settings (both websites, set at build time)**: `NEXT_PUBLIC_CURRENCY=NGN`, `NEXT_PUBLIC_LAUNCH_COUNTRIES=NG`. Without them prices still show a `$` and every country is offered.
**Terminal Africa**: `TERMINAL_CURRENCY=NGN` (the same as the charge currency, so no conversion rate is needed). Keep the SHIPPING_FLAT_FEE in mind: it is what a buyer pays whenever a live rate is not available.
**Prices**: every product price, the discount-code amounts and the minimum amounts are numbers in the charged currency. The seed data (demo products, the 4.99 and 50 delivery numbers) is dollar-sized; do not seed demo data into a naira production database.

**Paystack dashboard (do these before the first real order; items marked ? I could not confirm from here, ask Paystack)**
1. Webhook: `https://<backend>/payments/webhook`, and it must receive `charge.success`, `transfer.failed` and `transfer.reversed`.
2. Transfers must not need a confirmation code: Settings > Preferences, turn OFF the setting that makes you confirm transfers with an OTP. If it is on, every payout stops waiting for a code and the app reports it (it will not mark the seller as paid).
3. Money for payouts: payouts are sent from your Paystack BALANCE. Check your settlement schedule so customer payments stay in that balance long enough to be paid out (? a manual or delayed settlement schedule), or payouts will fail with "insufficient balance". Top the balance up if needed.
4. Ask Paystack that your use is allowed: you hold a buyer's payment for at least 48 hours and then transfer part of it to a seller (? whether they want that done through their subaccount/split-payment feature instead). This is a compliance question, not a code one, and it decides whether this design is allowed on your account.
5. Refunds: Paystack refunds go back to the buyer's card on their own schedule; the app refunds the order's share only.

**What happens when a payout fails**: a payout Paystack accepted but could not deliver (wrong account, bank down) comes back as `transfer.failed` or `transfer.reversed`; the order goes back to held, the seller gets a notification to check their bank details, and the next half-hourly sweep sends it again as a new transfer. After `MAX_PAYOUT_ATTEMPTS` (default 5) it stops and the log shows `PAYOUT STUCK` with the order id: someone must look. Watch for that line.
**What checkout now refuses**: a seller outside `LAUNCH_COUNTRIES` (when registering or changing the pickup address), a delivery address outside it, an order mixing sellers from another country, and a payment that comes back in a currency other than the charged one.
**Not built**: cross-border orders, and an admin screen to see stuck payouts (use the log and the Orders data for now).

## Trying the seller's order flow (live test, sealing) without a real buyer
`python -m app.seed --test-order SELLER_EMAIL [part of a product name]` puts one order for that seller's own product on their account, from a test buyer nobody can sign in as. It goes through the normal order code (stock is reserved), but its payment reference starts with `test-order-`, and the app then never pays the seller, never refunds and never books a courier for it. `python -m app.seed --remove-test-orders SELLER_EMAIL` deletes them and puts the stock back. **On Railway, with variables (no command needed):** in the backend service's Variables add `TEST_ORDER_FOR` = the seller's email (optionally `TEST_ORDER_PRODUCT` = part of a product name) and let it redeploy: the deploy adds ONE test order (it will not add another on later deploys). To remove it set `TEST_ORDER_REMOVE` = `true`, redeploy, then delete the variables. (The commands above also work from a shell.) The seller needs a product in stock and a pickup address saved. Not run against a real database yet.

## Renaming the platform

The name is read from one variable per service, then redeploy that service:

| Service | Variable | Where it shows |
|---|---|---|
| Backend | `APP_NAME` | emails, push titles, order and dispute messages, seal labels (PDF), authenticator label |
| Website | `NEXT_PUBLIC_APP_NAME` | every screen, legal pages, install name, notification fallback title, saved-file names |
| Admin | `NEXT_PUBLIC_APP_NAME` | panel title, sign-in page |
| Native shell | `LUMIN_APP_NAME` (before `npx cap sync` and `node scripts/apply-android.mjs`) | name under the app icon, Android quick-settings tile |

Use the same value everywhere. Not changed by these variables, by design: the logo and splash pictures (`lumin-app/public/brand/`), the demo
data names made by the seed (`Lumin Express`, `Lumin Demo Shop`, ...), the app's bundle id / package name (`app.lumin.scan`, set once at the first
store upload), the iOS share/broadcast extension names (`Info.plist`), the native offline page text (`lumin-native/www/*.html`), and internal
identifiers (storage keys, CSS class names, the `LuminScan` plugin name).

## Errors from the website and admin panel

A screen that crashes in someone's browser is now reported. The website and the admin panel send a short report to the backend
(`POST /client-errors`, rate limited, no sign-in needed). Each report becomes one **warning line in the backend log**
(`client error [web/render] ... | page=/v/123 | ...`) and, if `SENTRY_DSN` is set on the backend, one Sentry event tagged `source` = `web` or `admin`.
- Nothing needs setting: the log line works as soon as this is deployed. Search the Railway backend log for `client error`.
- Kept: the message, a short stack, the page path (never the query string). Removed before keeping: tokens, e-mail addresses and anything
  that looks like a password or key. Nothing about who the person is, and nothing is stored in the database.
- Not reported on purpose: lost connections, cancelled requests and the browser's own harmless notices. At most 10 reports per page load.
- A screen that crashes while drawing now shows "Something went wrong / Try again" instead of a blank page (`app/error.tsx`).
- Not covered: crashes inside the native shell itself (Android/iOS code); those need Play Console / App Store Connect crash reports.

## Security
See `SECURITY_REVIEW.md`: what was fixed, and the open items. The one to decide before launch: a seller can declare an unsealed order delivered (payout after 24 h).

## Orders without a live test: moved by the platform courier
Needs migration 0051 (`alembic upgrade head`). Sellers never mark shipped / delivered. They tap **Ready for pickup** (needs their pickup
address). With `COURIER=terminal` Terminal's pickup and delivered events move the order (register the `shipment.*` webhook, see
`TERMINAL_SANDBOX_TEST.md`). With `COURIER=manual` your admins do it in Admin > Shipments: **Driver collected it**, then **Courier delivered it**.
Orders a seller marked shipped before this change (if any exist) appear at the top of Admin > Shipments as "Marked shipped by the seller, no courier record": confirm each with the seller or buyer, then press Delivered. A courier "delivered" event that arrives without a pickup event is treated as pickup then delivery.

## Orders nobody sends: automatic cancel and refund
A background sweep (every 10 minutes) cancels and refunds, and tells both sides: a pending order the seller never marked Ready for pickup (warned at 48 h, cancelled at 72 h) and an order whose driver was requested but never collected it (72 h after the request; the Terminal booking is cancelled too). An order already with a driver is never touched. Tune with Railway variables `AUTO_REMIND_UNPACKED_HOURS`, `AUTO_CANCEL_UNPACKED_HOURS`, `AUTO_CANCEL_UNCOLLECTED_HOURS` (defaults 48 / 72 / 72). Watch the logs for "automatic cancel of order ... failed": a failed refund is retried on the next sweep.

## Collect in person (machines and bulk goods)
Needs migrations 0052 and 0053. A seller ticks "Too big to post: buyer collects in person" on a product (they must have a pickup address saved; they can add optional visiting hours there). Buyers pay at checkout as normal (into escrow, no delivery fee for that product). The buyer then sees the seller's saved address, contact name, phone and visiting hours, and has `COLLECT_WINDOW_DAYS` (default 7) from payment to come. They can tap "I'm coming on ..." (the seller is notified), inspect the item, and tap Accept (order delivered, seller paid) or Reject with a reason (full refund, the item stays with the seller). A buyer who accepted cannot file a defect claim afterwards. The buyer gets one reminder 24 h before the window ends; after it the order is cancelled and refunded automatically. The seller is never chased to "pack" a collect order.
Known limits: the seller must watch for the order to show as delivered before handing the item over; a real person decides disputes about what was said at the inspection; the buyer still gives a delivery address at checkout (it fixes their country and currency); the window is one setting for every product (not per product).

Too heavy to post: any product heavier than `MAX_SHIPPABLE_GRAMS` (default 30000 = 30 kg) is always collect in person: the server switches it when the seller saves it (they need a pickup address), shows it that way to buyers, charges no courier fee, and refuses checkout if the seller has no pickup address. The listing form also suggests collect in person when the name or description sounds bulky (a hint only). A seller who understates the weight is not caught by this.
Size counts too (migration 0054): a posted product over `DIMENSIONS_REQUIRED_OVER_GRAMS` (default 5000 = 5 kg) must give its length, width and height in cm. The rule and the courier price use the bigger of the real weight and the volumetric weight (L x W x H / 5000 kg), so a big, light-looking crate is treated as heavy and, over the limit, becomes collect in person. Seller terms should also say: any extra courier charge caused by a wrong weight or size is taken from the seller's payout (not built yet: it needs Terminal's measured weight, see TERMINAL_SANDBOX_TEST.md).
Collect in person, more: the product page and cart show where it is collected from (city and state; the street only after payment). Checkout refuses a collect product whose seller has no pickup address or hasn't finished payout setup. Units bought together (same payment, same product) are accepted or rejected with one tap.
Collect in person, safety and oversight (migration 0055): a buyer who rejects chooses a reason. "I went and nobody was there" refunds them and adds a strike to the seller (no automatic penalty: you decide). Admin > Collect in person lists every collect order by outcome (rejected, seller not there, not collected, waiting, accepted) with the buyer's words, and a table of sellers with rejections or no-shows. Both buyer and seller screens carry safety advice.
"Nobody was there" now needs evidence (migration 0056): the buyer must have told the seller when they were coming (the time must have passed) and must attach a photo of the place from their phone camera. The buyer is refunded at once, but the seller only gets a strike after an admin confirms it in Admin > Collect in person, where both sides' photos and notes are shown. The seller is notified and has 48 hours to reply with a note and a photo (Orders screen). The photo box asks for the camera but a phone may still offer the gallery; location (GPS) check-in is not built.
Migration 0057: a claim against a seller is either "nobody was there" or "the seller was there but refused to show or sell it". Both need the planned time to have passed and a photo; the refused kind also needs a written account. Both refund the buyer at once and wait for the admin; a confirmed claim of either kind adds one strike.
