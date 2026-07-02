"""Toss API token status for Telegram UI."""

import html
import datetime
from zoneinfo import ZoneInfo

from app import App


def _format_remaining(seconds: int) -> str:
    if seconds <= 0:
        return "만료됨"
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours >= 1:
        return f"{hours}시간 {minutes}분 남음"
    if minutes >= 1:
        return f"{minutes}분 남음"
    return f"{secs}초 남음"


def _format_expires_at(expires_at: datetime.datetime | None) -> str:
    if expires_at is None:
        return ""
    kst = expires_at.astimezone(ZoneInfo("Asia/Seoul"))
    return kst.strftime("%m/%d %H:%M")


def format_toss_token_line(app: App, status: dict | None = None) -> str:
    """blockquote 밖용 — HTML 태그 없이 plain text (Telegram blockquote 중첩 금지)."""
    settings = app.settings
    if settings.dry_run:
        return "🔑 토스 토큰  🧪 DRY_RUN — 미사용"
    if not settings.has_toss:
        return "🔑 토스 토큰  🔴 키 없음 · .env 확인"

    status = status or {}
    reason = status.get("reason", "")
    remaining = int(status.get("remaining_seconds", 0))
    expires_at = status.get("expires_at")
    expires_str = _format_expires_at(expires_at)
    expiry_part = f" · 만료 {expires_str}" if expires_str else ""

    if reason == "refresh_failed":
        err = html.escape(str(status.get("error", "재발급 실패"))[:80])
        return f"🔑 토스 토큰  🔴 사용 불가 · {err}"

    if status.get("ok"):
        left = _format_remaining(remaining)
        return f"🔑 토스 토큰  🟢 사용 가능 · {left}{expiry_part}"

    if reason == "expiring_soon":
        left = _format_remaining(remaining)
        return f"🔑 토스 토큰  🟡 곧 갱신 · {left}{expiry_part}"

    if reason == "expired":
        return "🔑 토스 토큰  🔴 만료됨 · 재발급 필요"

    if reason == "missing":
        return "🔑 토스 토큰  ⚪ 없음 · 최초 발급 필요"

    return "🔑 토스 토큰  🔴 사용 불가"
