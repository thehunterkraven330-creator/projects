import uuid

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, uuid_pk


class MerchantAccount(Base, TimestampMixin):
    """Maps to MerchantAccount in lib/types.ts. One per user — the "v1
    scope" page.tsx's own comment describes above its `merchantAccount`
    state — enforced here with unique=True on user_id rather than a
    separate join table, since a second merchant account per user isn't
    a supported case yet.

    No shipping-fee settings here on purpose — delivery pricing belongs
    to whichever DeliveryCompany (models/delivery.py) actually fulfils
    it, not to the merchant selling the product. See that model's own
    comment, and compute_shipping_fee in app/shipping.py, for how a
    fee is actually resolved at checkout.
    """

    __tablename__ = "merchant_accounts"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    business_name: Mapped[str] = mapped_column(String(150))
    category: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(1000), default="")
    # Set together, once, by POST /merchant/payout — never edited
    # piecemeal, since account_name and paystack_recipient_code are both
    # derived FROM bank_code+account_number via Paystack's own API
    # (create_transfer_recipient in app/paystack.py), not independently
    # user-editable facts. All four null until a merchant actually adds
    # payout details; app/escrow.py's release_to_merchant refuses to pay
    # out to a merchant who hasn't yet.
    bank_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    account_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Resolved from Paystack, not typed in by the merchant — the point is
    # confirming "yes, this account number really does belong to this
    # name" before money ever gets sent to it.
    account_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    paystack_recipient_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Stripe Connect (app/stripe_gateway.py): the seller's Express account (acct_...), created when they tap "Set up payouts".
    # Stripe collects their identity and bank details itself, so no bank numbers are stored here. `stripe_ready` caches "Stripe
    # says this seller can receive transfers and pay out to a bank" (set by the account.updated webhook / a live check).
    stripe_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    stripe_ready: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Keyword insights (what shoppers search for and can't find) are a paid
    # feature: active while this is in the future. Null = never subscribed.
    # Set by an admin for now (POST /admin/merchants/{id}/insights); the
    # Paystack subscription flow that renews it is not built yet.
    insights_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set when an admin approves the seller's identity documents (app/routers/verification.py); null = not verified.
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Where a courier collects this seller's sealed orders (Terminal Africa's "pickup address"). Set when the seller registers
    # and editable later from the dashboard. Flat nullable columns, like ShippingAddressMixin: existing sellers have none until
    # they add one. The country is a two-letter ISO code ("NG"), which is what courier APIs ask for.
    pickup_contact_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pickup_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    pickup_line1: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pickup_line2: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pickup_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pickup_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pickup_postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pickup_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    # When someone is there to meet a buyer who collects in person, e.g. "Mon to Sat, 9am to 5pm". Optional; shown to the buyer.
    # Times a buyer travelled to collect and reported that nobody was there (collect in person). Shown to admins; not automatic punishment.
    collect_no_show_strikes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pickup_visiting_hours: Mapped[str | None] = mapped_column(String(200), nullable=True)

    user: Mapped["User"] = relationship(back_populates="merchant_account")
    products: Mapped[list["Product"]] = relationship(back_populates="merchant")
    video_posts: Mapped[list["VideoPost"]] = relationship(back_populates="merchant")

    @property
    def has_pickup_address(self) -> bool:
        return all([self.pickup_contact_name, self.pickup_phone, self.pickup_line1, self.pickup_city, self.pickup_state, self.pickup_postal_code, self.pickup_country])
        # (the postal code counts: the courier cannot book without it, so a seller who saved an address before it was required is asked again)

    @property
    def pickup_address(self):
        """None until every required part is set; a plain dict that MerchantAccountRead validates into PickupAddress."""
        if not self.has_pickup_address:
            return None
        return {
            "contact_name": self.pickup_contact_name,
            "phone": self.pickup_phone,
            "line1": self.pickup_line1,
            "line2": self.pickup_line2,
            "city": self.pickup_city,
            "state": self.pickup_state,
            "postal_code": self.pickup_postal_code,
            "country": self.pickup_country,
            "visiting_hours": self.pickup_visiting_hours,
        }

    def set_pickup_address(self, a: dict) -> None:
        self.pickup_contact_name = a["contact_name"]
        self.pickup_phone = a["phone"]
        self.pickup_line1 = a["line1"]
        self.pickup_line2 = a.get("line2")
        self.pickup_city = a["city"]
        self.pickup_state = a["state"]
        self.pickup_postal_code = a.get("postal_code")
        self.pickup_country = a["country"]
        self.pickup_visiting_hours = (a.get("visiting_hours") or "").strip() or None

    # Not a column — see paystack_recipient_code's own comment. Picked
    # up by MerchantAccountRead (from_attributes) the same way
    # Product.in_stock is picked up by ProductRead.
    @property
    def payout_ready(self) -> bool:
        if self.payout_provider == "stripe":
            return bool(self.stripe_account_id) and bool(self.stripe_ready)
        return self.paystack_recipient_code is not None

    @property
    def payout_provider(self) -> str:
        """How this seller is paid, from the country they collect from (app/countries.py)."""
        from app.payment_provider import merchant_provider

        return merchant_provider(self)

    @property
    def currency(self) -> str | None:
        """The currency this seller's prices are in: their country's (app/countries.py). None until they say where they ship from."""
        from app import countries

        r = countries.ROUTES.get((self.pickup_country or "").strip().upper())
        return r.currency if r is not None else None

    @property
    def verified(self) -> bool:
        return self.verified_at is not None

    @property
    def insights_active(self) -> bool:
        return self.insights_until is not None and self.insights_until > datetime.now(timezone.utc)
