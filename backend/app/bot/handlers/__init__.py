"""Router tree. Order matters: specific routers first, the fallback last."""

from aiogram import Router

from app.bot.handlers import cart, catalog, checkout, errors, orders, profile, start


def build_router() -> Router:
    root = Router(name="root")
    root.include_routers(
        errors.router,
        start.router,
        checkout.router,
        catalog.router,
        cart.router,
        orders.router,
        profile.router,
        start.fallback_router,
    )
    return root
