"""상태·모드 한글 라벨과 글리프 — HTML 없는 순수 텍스트."""

from __future__ import annotations

MODE_KO = {
    "ENTRY": "🌱 진입",
    "NORMAL_EARLY": "🌅 전반전",
    "NORMAL_LATE": "🌇 후반전",
    "REVERSE": "🔄 리버스",
    "FORCE_ONE": "⚡ 강제1회",
}

MODE_BRIEF = {
    "ENTRY": "진입",
    "NORMAL_EARLY": "전반전",
    "NORMAL_LATE": "후반전",
    "REVERSE": "리버스",
    "FORCE_ONE": "강제1회",
}

MARKET_STATUS_KO = {
    "regular": "🟢 장중",
    "premarket": "🟡 프리마켓",
    "afterhours": "🟡 애프터장",
    "day": "🟡 주간거래",
    "off_hours": "⏸️ 장외",
    "closed": "🔴 휴장",
}


def mode_label(mode: str, *, brief: bool = False) -> str:
    table = MODE_BRIEF if brief else MODE_KO
    return table.get(mode, str(mode).replace("_", " "))


def market_status_label(status: str) -> str:
    return MARKET_STATUS_KO.get(status, "⏸️ 장외")


def pnl_dot(positive: bool) -> str:
    return "🟢" if positive else "🔴"


def trend_arrow(positive: bool) -> str:
    """지수·등락 — pnl_dot 와 구분해서 사용."""
    return "▲" if positive else "▼"


def side_icon(side: str, *, style: str = "arrow") -> str:
    """매수/매도 표시. arrow=▲▼, dot=🟢🔴, text=글리프 없음."""
    is_buy = str(side).upper() == "BUY"
    if style == "arrow":
        return "▲" if is_buy else "▼"
    if style == "text":
        return ""
    return "🟢" if is_buy else "🔴"


def order_side(side: str) -> tuple[str, str]:
    return ("▲", "매수") if str(side).upper() == "BUY" else ("▼", "매도")


def month_bar(positive: bool) -> str:
    return "🟩" if positive else "🟥"


def badge_on(on: bool) -> str:
    return "🟢 ON" if on else "⚪ OFF"


def badge_live(dry: bool) -> str:
    return "🧪 DRY" if dry else "💹 LIVE"


def badge_bot(paused: bool) -> str:
    return "⏸️ 정지" if paused else "🤖 가동"


def badge_auto(paused: bool) -> str:
    return "⏸️ 멈춤" if paused else "⏰ 실행"


def _star_label(desc: str) -> str | None:
    plus = desc.find("+")
    pct_end = desc.find("%", plus)
    if plus >= 0 and pct_end > plus:
        return f"별 {desc[plus:pct_end + 1]}"
    return None


def short_order_label(desc: str, *, style: str = "plan") -> str:
    """주문 설명 → 짧은 라벨.

    style="plan"  : /plan 주문계획 (익절 매도 · 리버스 별매수 · 12자 절단)
    style="notify": 체결·접수 알림 (익절 · 리버스 매수 · 16자 절단)
    이전에는 plan_formatter 와 notifications 가 거의 같은 분기를 따로 갖고 있었다.
    """
    text = str(desc or "")
    is_plan = style == "plan"

    star_keys = ("별지점", "후반전 별") if is_plan else ("별지점",)
    if text.startswith("별 +") or any(k in text for k in star_keys):
        label = _star_label(text)
        if label:
            return label
        if is_plan:
            return "별지점"
    if "평단" in text and "별" not in text:
        return "평단"
    if "큰수" in text or "첫 진입" in text:
        return "큰수매수"
    if "하단 방어" in text or (is_plan and "방어" in text):
        for drop in (20, 30):
            if f"-{drop}%" in text:
                return f"하단방어 −{drop}%"
        if is_plan:
            return "하단방어"
    if "첫매도 MOC" in text or ("MOC" in text and "리버스" in text):
        return "리버스 MOC"
    if "LOC매도" in text and "리버스" in text:
        return "리버스 매도"
    if "쿼터매수" in text and "리버스" in text:
        return "리버스 쿼터매수"
    if is_plan and "리버스 쿼터" in text:
        return "리버스 쿼터"
    if "쿼터" in text:
        return "쿼터 매도"
    if "익절" in text:
        return "익절 매도" if is_plan else "익절"
    if is_plan and "강제1회" in text:
        return "강제1회"
    if "리버스" in text and "매수" in text:
        return "리버스 별매수" if is_plan else "리버스 매수"
    limit = 12 if is_plan else 16
    return text.split("(")[0].strip()[:limit]
