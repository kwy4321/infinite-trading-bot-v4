"""Format /start — home hub + symbol status."""

from __future__ import annotations

from app import App
from tg.format_helpers import dry_mode_reason, is_dry
from tg.status_formatter import format_status
from tg.ui import (
    badge_bot,
    badge_live,
    market_status_label,
    quote,
    section,
)


def format_home_status(app: App, token_line: str) -> str:
    try:
        market = market_status_label(app.broker.get_us_market_status())
    except Exception:
        market = market_status_label("off_hours")

    paused = app.runtime.is_paused()
    dry = is_dry(app)
    dry_hint = dry_mode_reason(app)
    mode_badge = badge_live(dry)
    if dry_hint:
        mode_badge += f" · {dry_hint}"

    header = section("라오어 무한매수 4.0", "🖥️")
    header += "\n" + quote(
        f"{badge_bot(paused)}   ·   {mode_badge}   ·   {market}",
        token_line,
    )
    return header + "\n\n" + format_status(app)
