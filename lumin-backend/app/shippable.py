"""Which products are too big to post. No imports from the rest of the app, so models, schemas and routers can all use it."""
import os

DEFAULT_MAX_SHIPPABLE_GRAMS = 30_000  # 30 kg
VOLUMETRIC_DIVISOR = 5000  # cm3 per kg: the usual courier rule (a box of 5000 cm3 is charged as 1 kg)
DEFAULT_DIMENSIONS_REQUIRED_OVER_GRAMS = 5_000  # 5 kg


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


def max_shippable_grams() -> int:
    """The heaviest single item that is sent by courier (MAX_SHIPPABLE_GRAMS, default 30 kg). Heavier: sold collect in person."""
    return _env_int("MAX_SHIPPABLE_GRAMS", DEFAULT_MAX_SHIPPABLE_GRAMS)


def dimensions_required_over_grams() -> int:
    """Above this declared weight a courier-delivered product must also give its size (DIMENSIONS_REQUIRED_OVER_GRAMS, default 5 kg)."""
    return _env_int("DIMENSIONS_REQUIRED_OVER_GRAMS", DEFAULT_DIMENSIONS_REQUIRED_OVER_GRAMS)


def chargeable_grams(weight_grams: "int | None", length_cm: "int | None" = None, width_cm: "int | None" = None, height_cm: "int | None" = None) -> "int | None":
    """What a courier charges by: the larger of the real weight and the volumetric weight (length x width x height / 5000 kg).
    None when nothing was given. A seller cannot call a 1 m x 1 m x 1 m crate "2 kg": it counts as 200 kg."""
    volumetric = None
    if length_cm and width_cm and height_cm:
        volumetric = int(length_cm * width_cm * height_cm / VOLUMETRIC_DIVISOR * 1000)
    candidates = [g for g in (weight_grams, volumetric) if g]
    return max(candidates) if candidates else None


def too_heavy_to_post(weight_grams: "int | None", length_cm: "int | None" = None, width_cm: "int | None" = None, height_cm: "int | None" = None) -> bool:
    grams = chargeable_grams(weight_grams, length_cm, width_cm, height_cm)
    return bool(grams) and grams > max_shippable_grams()


def needs_dimensions(weight_grams: "int | None", length_cm: "int | None", width_cm: "int | None", height_cm: "int | None") -> bool:
    """A product over the weight line that did not say how big it is."""
    return bool(weight_grams) and weight_grams > dimensions_required_over_grams() and not (length_cm and width_cm and height_cm)


def product_chargeable_grams(product) -> "int | None":
    return chargeable_grams(
        getattr(product, "weight_grams", None), getattr(product, "length_cm", None), getattr(product, "width_cm", None), getattr(product, "height_cm", None)
    )


def is_collect_only(product) -> bool:
    """True when buyers collect this product in person: the seller said so, or it is heavier (by weight or size) than the courier limit."""
    g = product_chargeable_grams(product)
    return bool(getattr(product, "collect_in_person", False)) or (bool(g) and g > max_shippable_grams())
