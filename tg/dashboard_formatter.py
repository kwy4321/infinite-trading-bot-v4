"""Text dashboard — alias for /status (진행상황)."""

from app import App
from tg.status_formatter import format_status


def format_dashboard(app: App) -> str:
    return format_status(app)
