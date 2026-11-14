# Security review (code reading, not a penetration test)

Done by reading the code and searching it: every route's sign-in requirement, who may touch which order, the payment and courier
webhooks, uploads, links the server fetches, secrets, headers. NOT done: running attacks against a live copy, auditing the npm and pip
packages (no network in the build sandbox), reading every line of business logic. Treat "no finding" as "nothing seen", not "safe".

## Fixed in this version
| # | Finding | Fix |
|---|---|---|
| 1 | A seller could set an order to "delivered" straight from "pending", or after it was cancelled and refunded (`PATCH /orders/{id}/status` took any status). "Delivered" starts the 24-hour countdown to the seller's payout, so an order that was never sent could still be paid out. | Only the next step is accepted: pending -> shipped -> delivered. Anything else is 409. Cancelling stays on its own route, which refunds. (`tests/test_order_status_steps.py`, needs the test database.) |
| 2 | The public list of who liked a video (`GET /video-posts/{id}/likes`) had no limit and no rate limit, so every account that ever liked a video could be pulled. | Capped at 200 names and 60 requests a minute. |
| 3 | No browser security headers on the website or admin panel. | `nosniff`, a referrer policy (a reset-password address is not passed to other sites), frame protection (admin: never framed), HSTS, and the "X-Powered-By" header removed. |

## Changed: the seller can never mark an order shipped or delivered
The server refuses it for every order. A seller taps **Ready for pickup**; the platform courier then moves the order: with
`COURIER=terminal`, Terminal's `shipment.in-transit` and `shipment.delivered` events; with `COURIER=manual`, an admin presses
**Driver collected it** and **Courier delivered it** in Admin > Shipments. Delivery starts the 24-hour claim window. **Still open:**
(1) for an order without a sealed bag the courier's "delivered" (or the admin's tap) is the only evidence, with no buyer code; (2) Terminal's
event field names are unverified until the sandbox test; (3) nothing cancels an order the courier never collects (reminder after 24 h, then
an admin settles it).

## Open: other findings
| Severity | Finding | Suggested action |
|---|---|---|
| Medium | The sign-in token lasts 7 days, is kept in the browser's local storage and cannot be revoked by the server. Anyone who steals it (for example through a script injected into a page) has the account for a week. There is no Content-Security-Policy to limit that. | Shorter token plus refresh, or a "token version" the server can bump on password change/logout; then a CSP, tested in staging (a wrong one blocks payments, video or uploads). |
| Low-medium | `scan_link.py` checks that a link's host is a public address, then the download looks the host up again. A hostile DNS server could answer differently the second time ("DNS rebinding") and point the download at an internal address. The other protections (ports, redirects re-checked, size and time caps) are good. | Download from the address that was checked (pin the IP), or fetch through a proxy that blocks private ranges. |
| Low | Live-test (evidence) uploads have no signed size, unlike normal uploads. A signed-in seller could upload a very large file to the evidence bucket (rate limited to 20 starts a minute, one link per test). | Sign the length like normal uploads, or set a storage quota/lifecycle rule on the bucket. |
| Low | Public endpoints write counters with no sign-in: sponsored card "reveal/click", product taps, view progress. They are rate limited (60/minute) but a script could still inflate click numbers. If advertisers are ever billed on clicks, count unique, signed-in or de-duplicated clicks. | Decide before sponsored placement is sold. |
| Info | `/docs`, `/redoc` and `/openapi.json` are hidden only when `ENVIRONMENT=production`. | Confirm that variable on the production backend. |
| Info | Admin accounts need two-step login by default (`REQUIRE_ADMIN_MFA` defaults to true) and cannot be created through the API. | Keep it true; make sure every admin has set up the authenticator. |
| Info | Dependencies were not audited. | Add `npm audit` and `pip-audit` to the CI workflow. |

## Looked at and fine
- No secret keys, tokens or private keys anywhere in the project files; the two `.env.local` files hold only a local address, and each
  sub-project ignores its env files in git.
- Every admin route sits behind `get_current_admin` at the router level (admin role + authenticator code), including new routes added
  later to those routers.
- Orders, live tests, bags and claims check that the signed-in person is the buyer or the selling merchant; unknown ids answer 404.
- Paystack (HMAC-SHA512), Stripe (signed event) and Terminal (HMAC-SHA512) webhooks verify the signature in constant time and refuse
  when no key is configured; the courier endpoints need the shared key.
- Passwords are hashed (bcrypt); reset tokens are random, stored only as a hash and expire; "forgot password" gives the same answer for
  unknown e-mails; sign-in, sign-up and reset are rate limited per address.
- The server-side link download blocks private and metadata addresses, odd ports and unlimited redirects, and caps size and time.
- Account lists (`PersonResult`) leave out e-mail, address and settings.
- Normal uploads sign the file type and exact size into the upload address.
- No hand-built SQL from user input (only `SELECT 1` for the health check).
