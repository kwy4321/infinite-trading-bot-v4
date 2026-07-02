"""Toss API token status for Telegram UI."""

import datetime
from zoneinfo import ZoneInfo

from app import App
from tg.ui import code, dim, row


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


def format_toss_token_row(app: App, status: dict) -> str:
    settings = app.settings
    if settings.dry_run:
        return row("🔑", "토스 토큰", dim("DRY_RUN — 미사용"))
    if not settings.has_toss:
        return row("🔑", "토스 토큰", "🔴 키 없음 · .env 확인")

    reason = status.get("reason", "")
    remaining = int(status.get("remaining_seconds", 0))
    expires_at = status.get("expires_at")
    expires_str = _format_expires_at(expires_at)

    if reason == "refresh_failed":
        err = status.get("error", "재발급 실패")
        return row("🔑", "토스 토큰", f"🔴 사용 불가 · {dim(err[:80])}")

    if status.get("ok"):
        left = _format_remaining(remaining)
        detail = f"{code(left)} · {dim(f'만료 {expires_str}')}" if expires_str else code(left)
        return row("🔑", "토스 토큰", f"🟢 사용 가능 · {detail}")

    if reason == "expiring_soon":
        left = _format_remaining(remaining)
        detail = f"{code(left)} · {dim(f'만료 {expires_str}')}" if expires_str else code(left)
        return row("🔑", "토스 토큰", f"🟡 곧 갱신 · {detail}")

    if reason == "expired":
        return row("🔑", "토스 토큰", "🔴 만료됨 · 재발급 필요")

    if reason == "missing":
        return row("🔑", "토스 토큰", "⚪ 없음 · 최초 발급 필요")

    return row("🔑", "토스 토큰", "🔴 사용 불가")
