"""Shared Telegram UI styling."""

DIVIDER = "────────────────"

MODE_KO = {
    "ENTRY": "🌱 진입",
    "NORMAL_EARLY": "🌅 전반전",
    "NORMAL_LATE": "🌇 후반전",
    "REVERSE": "🔄 리버스",
    "FORCE_ONE": "⚡ 강제1회",
}


def section(title: str, emoji: str = "") -> str:
    label = f"{emoji} {title}" if emoji else title
    return f"<b>{label}</b>\n{DIVIDER}"


def mode_label(mode: str) -> str:
    return MODE_KO.get(mode, mode.replace("_", " "))


def pnl_line(usd: float, pct: float) -> str:
    sign = "+" if usd >= 0 else ""
    icon = "📈" if usd >= 0 else "📉"
    return f"{icon} {sign}${usd:,.0f}  ({sign}{pct:.1f}%)"


MARKET_STATUS_KO = {
    "regular": "🟢 장중",
    "premarket": "🟡 프리마켓",
    "afterhours": "🟡 애프터장",
    "day": "🟡 주간거래",
    "off_hours": "⏸️ 장외",
    "closed": "🔴 휴장",
}


def market_status_label(status: str) -> str:
    return MARKET_STATUS_KO.get(status, "⏸️ 장외")


def help_block() -> str:
    return """\
<b>📊 현황</b>
/status — 📈 진행상황
/balance — 💼 계좌현황
/plan — 📋 오늘 주문계획

<b>⚙️ 설정</b>
/setting — 💰 원금 · 분할 · 큰수매수
/split — 📐 액면분할
/set_t — 🎯 T 값 조정

<b>📒 기록</b>
/dashboard — 📒 자산·손익 대시보드
/history — 🎓 종료 기록
/monthly — 📅 수익현황

<b>🔧 운영</b>
/pause — ⏸ 자동 실행 멈춤
/resume — ⏰ 자동 실행 재개
/run — ▶️ 수동 실행
"""
