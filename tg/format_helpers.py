"""Shared helpers for Telegram formatters."""

from app import App


def is_dry(app: App) -> bool:
    return app.settings.dry_run or not app.settings.has_toss


def resolve_price(app: App, symbol: str) -> float:
    """Best-effort market price; returns 0.0 on failure or DRY_RUN."""
    if is_dry(app):
        return 0.0
    try:
        pos = app.broker.get_holdings_item(symbol)
        price = float(pos.get("current_price") or 0)
        if price > 0:
            return price
        return float(app.broker.get_price(symbol) or 0)
    except Exception:
        return 0.0
