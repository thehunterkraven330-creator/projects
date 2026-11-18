from fastapi import APIRouter

from app import countries
from app.payment_provider import charge_currency

router = APIRouter(tags=["app-config"])


@router.get("/app-config")
def app_config():
    """What the app needs to know about this deployment before it can show a price. The currency comes from the server (the one
    buyers are charged in), so the screens never depend on a build setting reaching the web app: with one launch country it is that
    country's currency, otherwise the payment currency."""
    open_in = countries.enabled_countries()
    route = countries.route_for(open_in[0]) if len(open_in) == 1 else None
    return {"currency": route.currency if route else charge_currency(), "launch_countries": open_in}
