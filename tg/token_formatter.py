"""Toss API token status for Telegram UI."""

import html
import datetime
from zoneinfo import ZoneInfo

from app import App
from tg.ui import quote, section


def _format_remaining(seconds: int) -> str:
    if seconds <= 0:
        return "만료됨"
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours >= 1:
        return f"{hours}시간 {minutes}분"
    if minutes >= 1:
        return f"{minutes}분"
    return f"{secs}초"


def _format_expires_at(expires_at: datetime.datetime | None) -> str:
    if expires_at is None:
        return ""
    kst = expires_at.astimezone(ZoneInfo("Asia/Seoul"))
    return kst.strftime("%Y-%m-%d %H:%M")


def _is_usable(status: dict) -> bool:
    return bool(status.get("ok")) or status.get("reason") == "expiring_soon"


def format_toss_token_brief(app: App, status: dict | None = None) -> str:
    """/start용 — 사용 가능 여부만 (plain text)."""
    settings = app.settings
    if settings.dry_run:
        return "🔑 토스 토큰  🧪 DRY_RUN"
    if not settings.has_toss:
        return "🔑 토스 토큰  🔴 키 없음"

    status = status or {}
    if _is_usable(status):
        return "🔑 토스 토큰  🟢 사용 가능"
    return "🔑 토스 토큰  🔴 사용 불가"


def format_toss_token_detail(app: App, status: dict | None = None) -> str:
    """/token용 — 남은 시간·만료 시각 (blockquote 안은 plain text)."""
    settings = app.settings
    if settings.dry_run:
        return f"{section('토스 API 토큰', '🔑')}\n{quote('🧪 DRY_RUN — 토큰 미사용')}"
    if not settings.has_toss:
        return f"{section('토스 API 토큰', '🔑')}\n{quote('🔴 API 키 없음 · .env 확인')}"

    status = status or {}
    reason = status.get("reason", "")
    remaining = int(status.get("remaining_seconds", 0))
    expires_at = status.get("expires_at")
    expires_str = _format_expires_at(expires_at)

    if _is_usable(status):
        avail = "🟢 사용 가능"
    elif reason == "expired":
        avail = "🔴 만료됨"
    elif reason == "missing":
        avail = "⚪ 토큰 없음"
    elif reason == "refresh_failed":
        err = html.escape(str(status.get("error", "재발급 실패"))[:80])
        avail = f"🔴 사용 불가 · {err}"
    else:
        avail = "🔴 사용 불가"

    left = _format_remaining(remaining)
    expiry_line = expires_str if expires_str else "—"

    return (
        f"{section('토스 API 토큰', '🔑')}\n"
        + quote(
            f"상태  {avail}",
            f"남은 시간  {left}",
            f"만료 예정  {expiry_line} KST",
        )
    )
