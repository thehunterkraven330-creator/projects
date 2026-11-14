import uuid
from decimal import Decimal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from app.shippable import too_heavy_to_post


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    icon_url: str | None = None


class CategoryBannerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID
    title: str
    subtitle: str | None = None


class DealRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    text: str
    sub: str
    category_id: uuid.UUID | None = None


class ProductImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    position: int


class ProductBase(BaseModel):
    name: str
    price: Decimal
    description: str | None = None
    colors: list[str] = []
    sizes: list[str] = []
    is_new: bool = False
    # None (the default) means untracked/unlimited — see the same field
    # on the Product model for why. A merchant who wants stock enforced
    # sets a real number here; app/inventory.py's reserve_stock is what
    # actually enforces and decrements it at purchase time.
    stock_quantity: int | None = None
    # Shipping weight of one unit in grams (1 g to 100 kg), used to price delivery. None = not set yet.
    weight_grams: int | None = Field(default=None, ge=1, le=20_000_000)  # up to 20 tonnes: a machine is not a parcel
    # Sold "collect in person" (too big to post): no courier, no shipping fee. See Product.collect_in_person.
    collect_in_person: bool = False
    # Size of one packed unit in cm. Optional, but required above 5 kg for a product that is posted.
    length_cm: int | None = Field(default=None, ge=1, le=5000)
    width_cm: int | None = Field(default=None, ge=1, le=5000)
    height_cm: int | None = Field(default=None, ge=1, le=5000)
    # 0-100, None/0 meaning no discount — see the same field on the
    # Product model for what raising this actually triggers.
    discount_percent: int | None = None


class ProductCreate(ProductBase):
    banner_id: uuid.UUID | None = None
    # Becomes ProductImage rows on create — position is just this list's
    # index, matching the frontend's Product.images ordering.
    image_urls: list[str] = []


class ProductUpdate(BaseModel):
    """Every field optional — a PATCH only needs to send what's changing.
    image_urls, when present, REPLACES the product's whole image list
    (simpler than a separate add/remove/reorder API for a gallery this
    small); omit it entirely to leave existing images untouched."""

    name: str | None = None
    price: Decimal | None = None
    description: str | None = None
    colors: list[str] | None = None
    sizes: list[str] | None = None
    is_new: bool | None = None
    banner_id: uuid.UUID | None = None
    image_urls: list[str] | None = None
    # Distinguishing "leave stock alone" from "set it to unlimited" needs
    # the same exclude_unset handling the merchant router already gives
    # every other field here — see update_merchant_product in
    # routers/merchant.py, which reads this correctly via
    # model_dump(exclude_unset=True) rather than treating an omitted
    # field the same as an explicit null.
    stock_quantity: int | None = None
    weight_grams: int | None = Field(default=None, ge=1, le=20_000_000)
    collect_in_person: bool = False
    length_cm: int | None = Field(default=None, ge=1, le=5000)
    width_cm: int | None = Field(default=None, ge=1, le=5000)
    height_cm: int | None = Field(default=None, ge=1, le=5000)
    discount_percent: int | None = None


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # Read from Product.is_new_now (the flag, but only for NEW_ARRIVAL_DAYS after listing), so an old product stops being "new".
    is_new: bool = Field(default=False, validation_alias=AliasChoices("is_new_now", "is_new"))
    # What is charged: `price` less `discount_percent` (app/pricing.py). Equal to `price` when there is no discount.
    sale_price: Decimal
    cart_count: int
    # The currency `price` is in (the seller's country's); None until the seller says where they ship from.
    currency: str | None = None
    banner_id: uuid.UUID | None = None
    merchant_id: uuid.UUID | None = None
    images: list[ProductImageRead] = []
    # Not a column — a property on the model (see its own comment) that
    # from_attributes picks up here the same way. Saves the frontend from
    # reimplementing "stock_quantity is None or > 0" itself everywhere a
    # Buy/Add-to-cart button needs to know whether to disable.
    in_stock: bool = True
    # Collect-in-person products: the city and state it is collected from, shown before the buyer pays. None for everything else.
    collect_from: str | None = None
    # How many days the buyer has to come and decide (the server's COLLECT_WINDOW_DAYS), so the page never states a made-up number.
    collect_window_days: int | None = None

    @model_validator(mode="after")
    def _heavy_is_collect(self):
        # A product heavier than the courier limit is collect-in-person whatever the stored flag says (older listings, a changed limit).
        if too_heavy_to_post(self.weight_grams, self.length_cm, self.width_cm, self.height_cm):
            self.collect_in_person = True
        if self.collect_in_person:
            from app.models.commerce import collect_window_days  # here, not at the top: avoids an import loop

            self.collect_window_days = collect_window_days()
        return self
