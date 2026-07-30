"""Text dashboard — records asset overview (/dashboard)."""

from __future__ import annotations

from app import App
from tg.records_dashboard_formatter import format_records_dashboard


def format_dashboard(app: App) -> str:
    return format_records_dashboard(app)
