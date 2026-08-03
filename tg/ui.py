"""텔레그램 UI 프리미티브 — 구현은 render 패키지에 있다.

render 는 app/broker 에 의존하지 않는 순수 포맷 라이브러리라서,
도메인 코드(cycles, reporting)도 tg 를 import 하지 않고 같은 스타일을 쓸 수 있다.
새 포맷 함수는 render 에 추가하고 여기서 재노출한다.
"""

from __future__ import annotations

from render.html import (
    DIVIDER,
    DOTS,
    TELEGRAM_MAX_LEN,
    THIN,
    bold,
    card,
    code,
    dim,
    esc,
    quote,
    quote_exp,
    split_html,
    strip_tags,
    validate_html,
)
from render.labels import (
    MARKET_STATUS_KO,
    MODE_BRIEF,
    MODE_KO,
    badge_auto,
    badge_bot,
    badge_live,
    badge_on,
    market_status_label,
    mode_label,
    month_bar,
    order_side,
    pnl_dot,
    side_icon,
    trend_arrow,
)
from render.numbers import (
    empty,
    krw,
    pct,
    pnl_line,
    pnl_line_brief,
    pnl_line_precise,
    row,
    section,
    signed_usd_text,
    subsection,
    symbol_card,
    t_transition,
    usd,
)

__all__ = [
    "DIVIDER", "DOTS", "THIN", "TELEGRAM_MAX_LEN",
    "MARKET_STATUS_KO", "MODE_BRIEF", "MODE_KO",
    "badge_auto", "badge_bot", "badge_live", "badge_on", "bold", "card", "code",
    "dim", "empty", "esc", "help_block", "krw", "market_status_label", "mode_label",
    "month_bar", "order_side", "pct", "pnl_dot", "pnl_line", "pnl_line_brief",
    "pnl_line_precise", "quote", "quote_exp", "row", "section", "side_icon",
    "signed_usd_text", "split_html", "strip_tags", "subsection", "symbol_card",
    "t_transition", "trend_arrow", "usd", "validate_html",
]


def help_block() -> str:
    """/help 명령 목록 — 텔레그램 전용이므로 render 로 내리지 않는다."""
    groups = [
        ("♾️ 현황", [
            (code("/status"), "♾️ 무매 진행상황"),
            (code("/balance"), "💼 계좌현황"),
            (code("/plan"), "📋 오늘 주문계획"),
        ]),
        ("⚙️ 설정", [
            (code("/setting"), "💰 원금·분할·큰수매수"),
            (code("/split"), "📐 액면분할"),
            (code("/set_t"), "🎯 T 값 조정"),
            (code("/token"), "🔑 API 토큰 상태·갱신"),
        ]),
        ("🔧 운영", [
            (code("/pause"), "⏸ 자동 실행 멈춤"),
            (code("/resume"), "⏰ 자동 실행 재개"),
            (code("/run"), "▶️ 수동 실행"),
        ]),
    ]
    blocks = []
    for title, cmds in groups:
        rows = [f"{cmd}　{dim(desc)}" for cmd, desc in cmds]
        blocks.append(f"{subsection(title)}\n{quote(*rows)}")
    return "\n".join(blocks)
