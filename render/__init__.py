"""표현(포맷) 계층 — 순수 문자열 포맷 라이브러리.

core 와 표준 라이브러리만 import 한다. app/broker/state 를 절대 참조하지 않는다.
덕분에 도메인 코드(cycles, reporting 등)가 tg 패키지를 끌어오지 않고도
텔레그램 HTML 을 만들 수 있다.
"""

from render.html import (  # noqa: F401
    DIVIDER,
    DOTS,
    THIN,
    TELEGRAM_MAX_LEN,
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
from render.labels import (  # noqa: F401
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
    short_order_label,
    side_icon,
    trend_arrow,
)
from render.numbers import (  # noqa: F401
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
