"""Toss API token status for Telegram UI."""

from __future__ import annotations

import html
import datetime
from zoneinfo import ZoneInfo

from config.toss_credentials import format_toss_credential_help, mask_credential
from tg.format_helpers import dry_mode_reason, is_dry
from tg.ui import dim, quote, section


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
    if not settings.has_toss:
        return "🔑 토스 토큰  🔴 키 없음"
    if is_dry(app):
        return "🔑 토스 토큰  🧪 DRY_RUN"

    status = status or {}
    if _is_usable(status):
        return "🔑 토스 토큰  🟢 사용 가능"
    return "🔑 토스 토큰  🔴 사용 불가"


def format_toss_token_detail(app: App, status: dict | None = None) -> str:
    """/token용 — 남은 시간·만료 시각 (blockquote 안은 plain text)."""
    settings = app.settings
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
        avail = "⚪ 캐시 없음 — 상태 확인 시 자동 발급"
    elif reason == "no_credentials":
        avail = "🔴 API 키 없음 · .env TOSS_CLIENT_ID/SECRET"
    elif reason == "refresh_failed":
        raw = str(status.get("error", "재발급 실패"))
        err = html.escape(raw[:160])
        prefix = "⚠️ 갱신 실패(기존 토큰 유지)" if remaining > 0 else "🔴 갱신 실패"
        avail = f"{prefix} · {err}"
        if "edge-blocked" in raw or "허용 IP" in raw:
            avail += f"\n{dim('WTS 설정 > Open API > 허용 IP 관리에 서버 공인 IP 등록')}"
        elif "invalid_client" in raw:
            hints = " · ".join(format_toss_credential_help(auth_401=True)[:3])
            avail += f"\n{dim(hints)}"
    else:
        avail = "🔴 사용 불가"

    left = _format_remaining(remaining)
    expiry_line = expires_str if expires_str else "—"
    dry_note = ""
    if is_dry(app):
        hint = dry_mode_reason(app) or "DRY_RUN"
        dry_note = f"\n{dim(f'🧪 {hint} — 토큰 갱신·검증은 가능, 주문은 시뮬')}"

    cred_hint = ""
    if reason == "refresh_failed" and settings.has_toss:
        cid = mask_credential(settings.toss_client_id)
        cred_hint = f"\n{dim(f'로드된 ID: {cid} — WTS 재발급 키와 앞 4자·길이 비교')}"

    return (
        f"{section('토스 API 토큰', '🔑')}\n"
        + quote(
            f"상태  {avail}",
            f"남은 시간  {left}",
            f"만료 예정  {expiry_line} KST",
        )
        + cred_hint
        + dry_note
    )
