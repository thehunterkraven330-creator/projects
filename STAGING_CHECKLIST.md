# Staging run: one pass through the whole system

Purpose: find what the build sandbox cannot (real database, real payment providers in test mode, Terminal's real replies, a production
build, real phones). Do it on a STAGING copy of the project on Railway, never on production: test keys only, test data only.
Tick each line. For every line that fails, write down the screen, what you did, what you saw, and the Railway log lines around it.
Never paste secret keys, card numbers or passwords in a chat or a file.

## A. Set up staging (once)
- [ ] A second Railway environment with its OWN database (copy the project into "staging"). Same code as the zip you will deploy.
- [ ] Backend variables: `LAUNCH_COUNTRIES` (just the country you are testing first, e.g. `NG`), that country's provider TEST keys
      (`PAYSTACK_SECRET_KEY` + `PAYSTACK_PUBLIC_KEY` for NG, or `STRIPE_SECRET_KEY` + `STRIPE_PUBLIC_KEY` + `STRIPE_WEBHOOK_SECRET`
      for US/GB), `FRONTEND_URL`, `CORS_ORIGINS`, `APP_NAME` if you are renaming, and the storage variables from LAUNCH.md.
- [ ] Website variables: `NEXT_PUBLIC_LAUNCH_COUNTRIES` (same list), `NEXT_PUBLIC_APP_NAME` if renaming. Admin: `NEXT_PUBLIC_APP_NAME`.
- [ ] Deploy backend first. The deploy log shows migrations running to 0050 and no error; the service starts. (A missing key for a
      country in `LAUNCH_COUNTRIES` stops the start on purpose: the log says which.)
- [ ] Deploy website and admin. Both open. `next build` passed (a failed build shows in the Railway build log: send me that text).
- [ ] Register the payment webhook in the provider's test dashboard: Paystack `https://<backend>/payments/webhook`, Stripe
      `https://<backend>/payments/stripe-webhook` (check the exact prefix in the deploy docs if the call returns 404).
- [ ] Make three accounts: a seller (complete pickup address, a product in stock), a buyer (complete delivery address), an admin.

## B. Payments (test mode)
Test cards are the provider's own; look them up in the provider's test docs (Paystack and Stripe both publish them).
- [ ] Buyer adds the product to the cart (from the product page AND from the category list: "Add to cart" button) and checks out.
- [ ] Pay with the test card. The order shows as paid; the seller sees it under their orders.
- [ ] A declined test card shows a clear error and creates no paid order.
- [ ] The provider's dashboard shows the test payment, and the webhook shows delivered (a failed delivery here is a finding).
- [ ] Seller: live test (see D), seal the bag, then the buyer confirms delivery. The seller's payout is made in test mode, no error.
- [ ] Refund path: a second order, buyer reports a problem, admin resolves it as a refund. The refund appears in the provider's dashboard.
- [ ] Wrong-country order: a buyer in another country cannot buy from this seller (orders must be domestic).

## C. Terminal Africa (sandbox)
Follow `TERMINAL_SANDBOX_TEST.md` (quote at checkout, booking when the bag is sealed, status webhook). Do B first: C reuses a paid order.

## D. Screens, on a CHEAP phone over MOBILE DATA (not your own phone on Wi-Fi)
Changed recently: each of these was only checked for syntax, never seen running.
- [ ] Open the app. First video plays. Write down the seconds from tapping the icon to the first frame.
- [ ] Swipe through 10 videos up and down. Count the spinners or black frames. Swipe back to the previous video.
- [ ] Discover opens (with an empty feed it shows the note, not a blank screen).
- [ ] Search: type a word, press Enter, open a result. Clear the box: "Recent" lists that search; tap it; the ✕ removes it; "Clear all" works;
      after logging out and in, Recent is empty.
- [ ] Category screen: product pictures show in the "See more" row and the list; "Add to cart" works; a product with several sizes says
      "Choose options".
- [ ] Open each of these once and note any blank flash on first open: cart, profile, settings, comments, product page, notifications,
      my orders, wanted board, seller dashboard, login.
- [ ] Seller: new product form: if a category has no collection, the product still saves; the Collection field is optional there.
- [ ] Live test: "Go live test" opens the intro. Start, then "Cancel test" asks "Discard this recording?"; Keep recording continues,
      Discard leaves. The phone back gesture while filming asks the same question. Finish a full test: scan the bag, upload, done.
      Back arrow on the intro screen leaves. Leaving while the camera is starting turns the camera light off.
- [ ] Likes: like a video, leave, come back, reload the app: the count includes your like. React to a comment (Like, Love) and do the same.
      If a count is wrong, write down the number before and after and look for the request in the log (`.../like` or `.../reaction`).
- [ ] Scan: scan a known video. Write down the seconds. In the backend log find the `scan timing:` line and send it to me.
- [ ] Rename: with `APP_NAME` / `NEXT_PUBLIC_APP_NAME` set to a different name, no screen, email or notification still says "Lumin"
      (the logo pictures and demo data are known exceptions, see LAUNCH.md).
- [ ] Admin panel opens, shows the staging data, and the title shows the name you set.

## E. Numbers to write down
| What | Result |
|---|---|
| Icon tap to first video (s) | |
| Spinners in 10 swipes | |
| Scan time, 3 scans (s) | |
| `scan timing:` lines | |
| Checkout, tap Pay to paid screen (s) | |
| Anything that showed a blank screen | |

## F. Result
- [ ] Every line in A–D ticked, or each failure written up as: screen, steps, what you saw, log lines.
Send me the failures. Fix them in staging, then repeat only the lines that failed plus B, before anything goes near production.
