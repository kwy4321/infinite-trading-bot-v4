"""Shared Telegram UI styling — HTML-safe (Telegram parse_mode=HTML)."""

DIVIDER = "━━━━━━━━━━━━━━━━"
THIN = "┈┈┈┈┈┈┈┈┈┈┈┈"
DOTS = "· · · · · · · · · · · ·"


def quote(*lines) -> str:
    """카드처럼 보이는 인용 박스 (왼쪽 세로 바)."""
    body = "\n".join(str(line) for line in lines if line is not None)
    return f"<blockquote>{body}</blockquote>"


def quote_exp(*lines) -> str:
    """접을 수 있는 인용 박스 — 긴 목록(기록 등)에 사용."""
    body = "\n".join(str(line) for line in lines if line is not None)
    return f"<blockquote expandable>{body}</blockquote>"

MODE_KO = {
    "ENTRY": "🌱 진입",
    "NORMAL_EARLY": "🌅 전반전",
    "NORMAL_LATE": "🌇 후반전",
    "REVERSE": "🔄 리버스",
    "FORCE_ONE": "⚡ 강제1회",
}

MARKET_STATUS_KO = {
    "regular": "🟢 장중",
    "premarket": "🟡 프리마켓",
    "afterhours": "🟡 애프터장",
    "day": "🟡 주간거래",
    "off_hours": "⏸️ 장외",
    "closed": "🔴 휴장",
}


def section(title: str, emoji: str = "") -> str:
    label = f"{emoji} {title}" if emoji else title
    return f"<b>{label}</b>\n{DIVIDER}"


def subsection(title: str) -> str:
    return f"<b>▸ {title}</b>"


def mode_label(mode: str) -> str:
    return MODE_KO.get(mode, mode.replace("_", " "))


def market_status_label(status: str) -> str:
    return MARKET_STATUS_KO.get(status, "⏸️ 장외")


def code(text: str) -> str:
    """Monospace highlight — reads like a distinct color in Telegram."""
    return f"<code>{text}</code>"


def dim(text: str) -> str:
    return f"<i>{text}</i>"


def bold(text: str) -> str:
    return f"<b>{text}</b>"


def usd(amount: float, decimals: int = 2, signed: bool = False) -> str:
    sign = ""
    if signed and amount > 0:
        sign = "+"
    return code(f"{sign}${amount:,.{decimals}f}")


def krw(amount: float, signed: bool = False) -> str:
    sign = ""
    if signed and amount > 0:
        sign = "+"
    return code(f"{sign}₩{amount:,.0f}")


def pct(value: float, signed: bool = True) -> str:
    sign = "+" if signed and value > 0 else ""
    if not signed and value > 0:
        sign = "+"
    return dim(f"({sign}{value:.1f}%)")


def pnl_dot(positive: bool) -> str:
    return "🟢" if positive else "🔴"


def pnl_line(usd: float, pct_val: float) -> str:
    pos = usd >= 0
    sign = "+" if usd >= 0 else ""
    return f"{pnl_dot(pos)} {code(f'{sign}${usd:,.0f}')}  {pct(pct_val)}"


def pnl_line_precise(usd: float, pct_val: float) -> str:
    pos = usd >= 0
    sign = "+" if usd >= 0 else ""
    return f"{pnl_dot(pos)} {code(f'{sign}${usd:,.2f}')}  {pct(pct_val)}"


def row(emoji: str, label: str, value: str) -> str:
    return f"{emoji} {dim(label)}  {value}"


def symbol_card(symbol: str) -> str:
    return f"◆ {bold(symbol)}"


def empty(msg: str = "데이터 없음") -> str:
    return f"📭 <i>{msg}</i>"


def badge_on(on: bool) -> str:
    return "🟢 ON" if on else "⚪ OFF"


def badge_live(dry: bool) -> str:
    return "🧪 DRY" if dry else "💹 LIVE"


def badge_bot(paused: bool) -> str:
    return "⏸️ 정지" if paused else "🤖 가동"


def badge_auto(paused: bool) -> str:
    return "⏸️ 멈춤" if paused else "⏰ 실행"


def order_side(side: str) -> tuple[str, str]:
    if side.upper() == "BUY":
        return "🟢", "매수"
    return "🔴", "매도"


def month_bar(positive: bool) -> str:
    return "🟩" if positive else "🟥"


def help_block() -> str:
    groups = [
        ("📊 현황", [
            (f"{code('/status')}", "📈 진행상황"),
            (f"{code('/balance')}", "💼 계좌현황"),
            (f"{code('/plan')}", "📋 오늘 주문계획"),
        ]),
        ("⚙️ 설정", [
            (f"{code('/setting')}", "💰 원금·분할·큰수매수"),
            (f"{code('/split')}", "📐 액면분할"),
            (f"{code('/set_t')}", "🎯 T 값 조정"),
        ]),
        ("📒 기록", [
            (f"{code('/dashboard')}", "📒 자산·손익 대시보드"),
            (f"{code('/history')}", "🎓 종료 기록"),
            (f"{code('/monthly')}", "📅 수익현황"),
        ]),
        ("🔧 운영", [
            (f"{code('/pause')}", "⏸ 자동 실행 멈춤"),
            (f"{code('/resume')}", "⏰ 자동 실행 재개"),
            (f"{code('/run')}", "▶️ 수동 실행"),
        ]),
    ]
    blocks = []
    for title, cmds in groups:
        rows = [f"{cmd}　{dim(desc)}" for cmd, desc in cmds]
        blocks.append(f"{subsection(title)}\n{quote(*rows)}")
    return "\n".join(blocks)
