"""Format /start — home hub (하단 메뉴 안내)."""

from app import App
from tg.format_helpers import is_dry
from tg.ui import (
    badge_bot,
    badge_live,
    dim,
    market_status_label,
    quote,
    row,
    section,
    subsection,
)


def format_home(app: App, token_line: str) -> str:
    try:
        market = market_status_label(app.broker.get_us_market_status())
    except Exception:
        market = market_status_label("off_hours")

    paused = app.runtime.is_paused()
    dry = is_dry(app)

    lines = [
        section("라오어 무한매수 4.0", "🖥️"),
        quote(
            f"{badge_bot(paused)}   ·   {badge_live(dry)}   ·   {market}",
            token_line,
        ),
        "",
        subsection("하단 메뉴"),
        quote(
            row("📋", "주문계획", dim("오늘 LOC 매수·매도 계획")),
            row("📈", "현황", dim("T · 회차 · 보유 · 전략 모드")),
            row("💼", "잔고", dim("토스 예수금 · 종목 평가")),
            row("⚙️", "설정", dim("원금 · 분할 · 거래 종목")),
            row("🔑", "토큰", dim("만료 시각 · 갱신")),
        ),
        "",
        subsection("추가 명령"),
        quote(
            dim("/dashboard  자산·손익 요약"),
            dim("/cycles  회차 기록  ·  /sync  실계좌 동기화"),
            dim("/run  수동 실행  ·  /pause  /resume"),
        ),
    ]
    return "\n".join(lines)
