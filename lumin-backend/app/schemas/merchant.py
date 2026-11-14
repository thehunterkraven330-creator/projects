import uuid

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PickupAddress(BaseModel):
    """Where a courier collects this seller's orders (sent to the courier, e.g. Terminal Africa, as the pickup address).
    Everything but line2 is required: a driver cannot be sent without them, and the courier needs the postal code to book. `country` is a two-letter ISO code."""

    model_config = ConfigDict(from_attributes=True)

    contact_name: str
    phone: str
    line1: str
    line2: str | None = None
    city: str
    state: str
    postal_code: str
    country: str
    visiting_hours: str | None = Field(default=None, max_length=200)  # optional: when someone is there for buyers who collect in person

    @field_validator("contact_name", "phone", "line1", "city", "state", "postal_code", mode="before")
    @classmethod
    def _required_text(cls, v):
        v = (v or "").strip() if isinstance(v, str) or v is None else v
        if not v:
            raise ValueError("This field is required")
        return v

    @field_validator("line2", mode="before")
    @classmethod
    def _optional_text(cls, v):
        return (v.strip() or None) if isinstance(v, str) else v

    @field_validator("country", mode="before")
    @classmethod
    def _country(cls, v):
        v = (v or "").strip().upper() if isinstance(v, str) or v is None else v
        if not re.fullmatch(r"[A-Z]{2}", v or ""):
            raise ValueError("Country must be a two-letter code such as NG")
        from app import market

        if not market.is_open_in(v):
            raise ValueError(market.seller_message())
        return v

    @model_validator(mode="after")
    def _phone_for_country(self):
        """Kept in the international form ('+2348122340000'): that is what the courier takes, and it proves the number is real."""
        from app.phone import to_e164

        self.phone = to_e164(self.phone, self.country)  # ValueError -> a 422 with its message
        return self


class MerchantAccountBase(BaseModel):
    business_name: str
    category: str
    description: str = ""


class MerchantAccountCreate(MerchantAccountBase):
    # Collected at registration: the courier needs it to collect the first sealed order.
    pickup_address: PickupAddress


class MerchantAccountUpdate(BaseModel):
    """PATCH /merchant/account — every field optional, applied with
    exclude_unset (same convention as UserUpdate). No dashboard UI edits
    any of these yet, so nothing currently calls this route at all — kept
    in place for when one exists, rather than removed and rebuilt later.
    Shipping settings deliberately aren't here: pricing delivery is
    DeliveryCompany's job (models/delivery.py), not something a merchant
    account has ever been able to configure.
    """

    business_name: str | None = None
    category: str | None = None
    description: str | None = None
    # Replaces the whole address (a half-edited address is useless to a courier), so send every required field.
    pickup_address: PickupAddress | None = None


class MerchantAccountRead(MerchantAccountBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    # All null until POST /merchant/payout succeeds. account_name is
    # resolved from Paystack, not typed in — see the model's own comment
    # on why. paystack_recipient_code itself is deliberately NOT exposed
    # here (internal-only, nothing on the frontend needs the raw code);
    # payout_ready is what a "add your payout details" UI should actually
    # check instead.
    bank_code: str | None = None
    account_number: str | None = None
    account_name: str | None = None
    payout_ready: bool = False
    # "stripe" or "paystack": decides which payout setup the app shows.
    payout_provider: str = "paystack"
    # Keyword insights subscription state (see MerchantAccount.insights_until).
    insights_active: bool = False
    # An admin approved this seller's identity documents (routers/verification.py).
    verified: bool = False
    # Null until the seller has given a complete pickup address (existing sellers start without one).
    pickup_address: PickupAddress | None = None


class MerchantPayoutCreate(BaseModel):
    """POST /merchant/payout. Just enough to resolve+verify the account
    and create a Paystack transfer recipient from it — see
    create_transfer_recipient in app/paystack.py for what actually
    happens with these two fields.
    """

    bank_code: str
    account_number: str


class BankRead(BaseModel):
    """GET /merchant/banks — just enough for a picker UI. Paystack's own
    /bank response has more fields than this; everything else gets
    dropped automatically by using this as the response_model rather
    than passed through raw.
    """

    name: str
    code: str
