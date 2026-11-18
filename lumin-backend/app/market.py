"""Which countries Lumin is open in: the ones switched on in app/countries.py (LAUNCH_COUNTRIES; unset = wave 1: NG, US, GB).

Sellers must collect from one of them, buyers can only have orders delivered to one, and an order must be domestic: a buyer is
never sold something from a seller in another country (that would mean two currencies and, with two payment providers, money
moving between them; see LAUNCH.md). Kept free of app imports so schemas and routers can both use it.
"""
from app import countries

NAMES = {
    "NG": "Nigeria", "GH": "Ghana", "KE": "Kenya", "ZA": "South Africa", "US": "the United States", "GB": "the United Kingdom",
    "CA": "Canada", "IE": "Ireland", "AU": "Australia", "CH": "Switzerland", "AT": "Austria", "BE": "Belgium", "DE": "Germany",
    "ES": "Spain", "FI": "Finland", "FR": "France", "IT": "Italy", "NL": "the Netherlands", "PT": "Portugal",
}


def launch_countries() -> list[str]:
    return countries.enabled_countries()


def is_open_in(country: str | None) -> bool:
    return (country or "").strip().upper() in launch_countries()


def _names(codes: list[str]) -> str:
    n = [NAMES.get(c, c) for c in codes]
    return n[0] if len(n) == 1 else ", ".join(n[:-1]) + " and " + n[-1]


def seller_message() -> str:
    return f"We're only taking sellers in {_names(launch_countries())} right now."


def delivery_message() -> str:
    return f"We only deliver to {_names(launch_countries())} right now."


def domestic_conflict(delivery_country: str | None, seller_countries: list[str | None]) -> bool:
    """True if any seller (who has said where they collect from) is in a different country from where this is delivered."""
    d = (delivery_country or "").strip().upper()
    return any(s and s.strip().upper() != d for s in seller_countries)
