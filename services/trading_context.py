"""DRY/LIVE 판정과 회차 가용 잔금 — 실행 컨텍스트 단일 소스."""

from __future__ import annotations

from typing import TYPE_CHECKING

from config.settings import is_dry_mode

if TYPE_CHECKING:
    from app import App


def is_dry(app: App) -> bool:
    """모의(DRY) 모드 여부 — 토스 키 미설정이거나 .env DRY_RUN 이면 True."""
    return is_dry_mode(app.settings, force_live=app.runtime.force_live())


def dry_mode_reason(app: App) -> str:
    """DRY 인 이유 한 줄. LIVE 면 빈 문자열."""
    if not is_dry(app):
        return ""
    if not app.settings.has_toss:
        return "토스 API 키 미설정"
    if app.settings.dry_run:
        return ".env DRY_RUN=true (설정→실거래 켜기)"
    return "알 수 없음"


def sync_broker_dry_run(app: App) -> None:
    """broker.dry_run 을 현재 설정과 일치시킨다. 조회·주문 전에 호출."""
    app.broker.dry_run = is_dry(app)


def resolve_available_cash(app: App, symbol: str, st: dict | None = None) -> float:
    """리버스 쿼터매수용 가용 잔금 ≈ 원금 − 매수 + 매도 (회차 기준).

    계산은 CycleTracker.available_cash 가 유일한 구현이다.
    """
    if st is None:
        st = app.state.load(symbol)
    principal = float(st.get("principal", 0.0) or 0.0)
    return app.cycles.available_cash(symbol, principal)
