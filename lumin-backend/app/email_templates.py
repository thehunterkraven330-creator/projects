"""Plain functions returning (subject, html) — no template engine, since
there are only two of these and neither has enough conditional structure
to earn one. Inline styles throughout (not a <style> block) because
that's what actually renders consistently across email clients; most
strip or ignore a <head><style> the way a browser wouldn't.
"""

from app.brand import APP_NAME, APP_NAME_HTML
from app.models import Order, Payment

# Symbols for the currencies we charge in. Anything else shows its code ("CHF 12.00"), never a wrong symbol.
_SYMBOLS = {"NGN": "₦", "USD": "$", "GBP": "£", "EUR": "€", "GHS": "GH₵", "KES": "KSh ", "ZAR": "R", "CAD": "CA$"}
_WHOLE = {"NGN", "KES", "GHS"}  # normally whole amounts: shown without ".00" when they are


def money(amount, currency: str) -> str:
    """1500 NGN -> "₦1,500"; 12 USD -> "$12.00". The currency is the one the buyer was charged in."""
    c = (currency or "").upper()
    value = float(amount)
    text = f"{value:,.0f}" if c in _WHOLE and value == int(value) else f"{value:,.2f}"
    symbol = _SYMBOLS.get(c)
    return f"{symbol}{text}" if symbol else f"{c} {text}".strip()

_WRAPPER_OPEN = f"""\
<div style="font-family: -apple-system, Helvetica, Arial, sans-serif; max-width: 480px; margin: 0 auto; color: #1a1a1a;">
  <h1 style="font-size: 20px; margin-bottom: 4px;">{APP_NAME_HTML}</h1>
"""
_WRAPPER_CLOSE = """
  <p style="margin-top: 32px; font-size: 12px; color: #888;">
    This is an automated message — please don't reply to this email.
  </p>
</div>
"""


def order_confirmation_email(orders: list[Order], payment: Payment) -> tuple[str, str]:
    """One email per Payment, covering every Order it produced —
    matches how a real receipt reads (one purchase, however many line
    items) rather than sending a separate email per Order row the way
    _fulfill's own per-unit expansion (a quantity-3 line becomes 3 Order
    rows) would otherwise suggest. Called once, from payments.py's
    _fulfill, with the exact list it just created.
    """
    from app.payment_provider import currency_of

    cur = currency_of(payment)
    address = payment.shipping_address
    rows = "".join(
        f"""
        <tr>
          <td style="padding: 8px 0; border-bottom: 1px solid #eee;">
            {order.product_name}{f" · {order.color}" if order.color else ""}{f" · {order.size}" if order.size else ""}
          </td>
          <td style="padding: 8px 0; border-bottom: 1px solid #eee; text-align: right;">
            {money(order.price, cur)}
          </td>
        </tr>"""
        for order in orders
    )
    subtotal = payment.amount - payment.shipping_fee + payment.discount_amount
    discount_row = (
        f"""
        <tr>
          <td style="padding: 4px 0; color: #16a34a;">Discount</td>
          <td style="padding: 4px 0; text-align: right; color: #16a34a;">-{money(payment.discount_amount, cur)}</td>
        </tr>"""
        if payment.discount_amount > 0
        else ""
    )
    address_html = (
        f"""
    <p style="font-size: 14px; line-height: 1.5;">
      {address["recipient_name"]}<br>
      {address["line1"]}{f", {address['line2']}" if address.get("line2") else ""}<br>
      {address["city"]}{f", {address['state']}" if address.get("state") else ""}
      {address.get("postal_code") or ""}<br>
      {address["country"]}
    </p>"""
        if address
        else ""
    )

    html = f"""{_WRAPPER_OPEN}
  <p style="font-size: 15px;">Thanks for your order! Here's your receipt.</p>
  <table style="width: 100%; border-collapse: collapse; font-size: 14px; margin: 16px 0;">
    {rows}
    <tr>
      <td style="padding: 8px 0 4px; font-size: 13px; color: #666;">Subtotal</td>
      <td style="padding: 8px 0 4px; text-align: right; font-size: 13px; color: #666;">{money(subtotal, cur)}</td>
    </tr>
    {discount_row}
    <tr>
      <td style="padding: 4px 0; font-size: 13px; color: #666;">Shipping</td>
      <td style="padding: 4px 0; text-align: right; font-size: 13px; color: #666;">{money(payment.shipping_fee, cur)}</td>
    </tr>
    <tr>
      <td style="padding: 8px 0 0; font-weight: bold; border-top: 1px solid #ddd;">Total</td>
      <td style="padding: 8px 0 0; text-align: right; font-weight: bold; border-top: 1px solid #ddd;">{money(payment.amount, cur)}</td>
    </tr>
  </table>
  <h2 style="font-size: 14px; margin-bottom: 4px;">Shipping to</h2>
  {address_html}
  <p style="font-size: 13px; color: #666;">
    Track this order any time under My Orders in your {APP_NAME_HTML} profile.
  </p>
{_WRAPPER_CLOSE}"""
    return f"Your {APP_NAME} order — {money(payment.amount, cur)}", html


def password_reset_email(reset_url: str) -> tuple[str, str]:
    """reset_url already has the raw token in it (routers/auth.py's
    forgot_password builds it) — this function only cares about
    rendering it, not generating or validating it.
    """
    html = f"""{_WRAPPER_OPEN}
  <p style="font-size: 15px;">
    Someone asked to reset the password on this account. If that was you,
    set a new one here — this link expires in 30 minutes:
  </p>
  <p style="margin: 24px 0;">
    <a href="{reset_url}"
       style="background: #FF6B35; color: #111114; padding: 10px 20px; border-radius: 999px;
              text-decoration: none; font-size: 14px; font-weight: bold;">
      Reset your password
    </a>
  </p>
  <p style="font-size: 13px; color: #666;">
    If you didn't request this, you can safely ignore this email — your
    password won't change unless you click the link above and set a new one.
  </p>
{_WRAPPER_CLOSE}"""
    return f"Reset your {APP_NAME} password", html


def verification_code_email(code: str, minutes: int) -> tuple[str, str]:
    html = f"""{_WRAPPER_OPEN}
  <p style="font-size: 15px;">
    Welcome to {APP_NAME_HTML}. Enter this code in the app to finish opening your account:
  </p>
  <p style="margin: 24px 0; font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #111114;">
    {code}
  </p>
  <p style="font-size: 13px; color: #666;">
    The code works for {minutes} minutes. If you didn't try to create a {APP_NAME_HTML} account, you can ignore this email.
  </p>
{_WRAPPER_CLOSE}"""
    return f"{code} is your {APP_NAME} code", html
