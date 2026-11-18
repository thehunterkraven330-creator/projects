import re

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class ShippingAddress(BaseModel):
    """Nested shape used in three places: as a saved default on
    UserRead, as what's sent once at checkout (PaymentInitializeCreate,
    or orders.py's OrderCreate for the legacy no-payment path) and never
    again per-order after that, and as the permanent snapshot read back
    on OrderRead. All three read this off a model's computed
    `shipping_address` property (see ShippingAddressMixin in
    models/base.py) — from_attributes validates straight off the dict
    that property returns.

    state and postal_code are optional — not every country's addressing
    scheme uses either. Every other field is required: this type
    describes a *complete, usable* address, not a form-in-progress (see
    ShippingAddressUpdate for that).
    """

    model_config = ConfigDict(from_attributes=True)

    recipient_name: str
    phone: str
    line1: str
    line2: str | None = None
    city: str
    state: str | None = None
    postal_code: str | None = None
    country: str


class ShippingAddressUpdate(BaseModel):
    """Same fields as ShippingAddress, all optional — PATCH /users/me
    accepts a partial address the same way it already accepts a partial
    display_name/bio (see UserUpdate's exclude_unset handling). Kept as
    its own type rather than reusing ShippingAddress with defaults,
    because "recipient_name omitted" and "recipient_name required but
    missing" need to mean different things here than they do on
    ShippingAddress itself.
    """

    recipient_name: str | None = None
    phone: str | None = None
    line1: str | None = None
    line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None


class ShippingAddressIn(ShippingAddress):
    """An address as the buyer ENTERS it (checkout, saving a default). Stricter than ShippingAddress, which is also what old
    saved addresses are read back as: the courier needs a two-letter country code, a postal code and a real phone number,
    and older addresses were typed as free text ("Nigeria", no postal code), so reading them must stay lenient."""

    @field_validator("postal_code", mode="before")
    @classmethod
    def _postal_required(cls, v):
        v = v.strip() if isinstance(v, str) else v
        if not v:
            raise ValueError("A postal code is required for delivery")
        return v

    @field_validator("country", mode="before")
    @classmethod
    def _country_code(cls, v):
        v = v.strip().upper() if isinstance(v, str) else v
        if not re.fullmatch(r"[A-Z]{2}", v or ""):
            raise ValueError("Country must be a two-letter code such as NG")
        from app import market

        if not market.is_open_in(v):
            raise ValueError(market.delivery_message())
        return v

    @model_validator(mode="after")
    def _phone_for_country(self):
        from app.phone import to_e164

        self.phone = to_e164(self.phone, self.country)  # ValueError -> a 422 with its message
        return self
