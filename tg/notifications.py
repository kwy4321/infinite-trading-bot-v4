"""Telegram notification text — 장시작·장마감·주문 접수·체결."""

from tg.ui import code, dim


def _side_ko(side: str) -> str:
    return "매수" if str(side).upper() == "BUY" else "매도"


def _side_icon(side: str) -> str:
    return "🟢" if str(side).upper() == "BUY" else "🔴"


def format_market_open(now_kst: str) -> str:
    return (
        f"🔔 <b>미국 장 시작</b>  <i>{now_kst} KST</i>\n"
        f"{dim('오늘 LOC 주문계획만 보내드려요. 실제 주문은 종가(한국 새벽)에 LIMIT+CLS로 들어갑니다.')}"
    )


def format_market_open_start(now_kst: str, symbol_count: int) -> str:
    sym = f"{symbol_count}종목" if symbol_count else "—"
    return (
        f"🔔 <b>미국 장 시작</b>  <i>{now_kst} KST</i>\n"
        f"예약 주문 접수 · {code(sym)}"
    )


def format_market_open_report(
    now_kst: str,
    symbol_lines: list[str],
    ok: int,
    total: int,
) -> str:
    """장 개장 예약 — 종목별 접수 결과."""
    header = f"🔔 <b>장 개장 예약 완료</b>  <i>{now_kst}</i>"
    if total <= 0:
        return f"{header}\n{dim('오늘 예약할 주문 없음')}"
    body = "\n".join(symbol_lines)
    footer = f"접수 {code(str(ok))}/{code(str(total))}건 · {dim('체결은 장중·새벽 sync 반영')}"
    return f"{header}\n\n{body}\n\n{footer}"


def format_market_close_start(now_kst: str, symbol_count: int) -> str:
    sym = f"{symbol_count}종목" if symbol_count else "—"
    return (
        f"🔔 <b>미국 장 마감</b>  <i>{now_kst} KST</i>\n"
        f"LOC 주문 실행 · {code(sym)}"
    )


def format_market_close_report(
    now_kst: str,
    symbol_lines: list[str],
    ok: int,
    total: int,
    filled: int,
) -> str:
    """장 마감 LOC — 종목별 결과 + 합계를 한 통으로."""
    header = f"🔔 <b>장 마감 완료</b>  <i>{now_kst}</i>"
    if total <= 0:
        return f"{header}\n{dim('오늘 실행할 주문 없음')}"
    body = "\n".join(symbol_lines)
    footer = (
        f"접수 {code(str(ok))}/{code(str(total))}건 · "
        f"체결 {code(str(filled))}건"
    )
    return f"{header}\n\n{body}\n\n{footer}"


def format_order_submitted(
    symbol: str,
    side: str,
    qty: int,
    label: str,
    *,
    order_id: str = "",
    dry: bool = False,
    loc: bool = False,
) -> str:
    tag = f"  {dim('[DRY]')}" if dry else ""
    kind = f"  {dim('LOC')}" if loc else ""
    oid = f"\n{dim('주문')} {code(order_id)}" if order_id else ""
    return (
        f"📥 <b>{symbol}</b> {_side_ko(side)} <b>접수</b>{tag}{kind}\n"
        f"{_side_icon(side)} {label} · {code(f'{qty}주')}{oid}"
    )


def format_order_filled(
    symbol: str,
    side: str,
    qty: int,
    price: float,
    label: str,
    *,
    dry: bool = False,
) -> str:
    tag = f"  {dim('[DRY]')}" if dry else ""
    price_txt = code(f"${price:,.2f}") if price > 0 else code("—")
    return (
        f"✅ <b>{symbol}</b> {_side_ko(side)} <b>체결</b>{tag}\n"
        f"{_side_icon(side)} {label} · {code(f'{qty:g}주')} @ {price_txt}"
    )


def format_order_not_filled(
    symbol: str,
    side: str,
    label: str,
    status: str,
) -> str:
    st = status or "미체결"
    return (
        f"⚠️ <b>{symbol}</b> {_side_ko(side)} {dim('미체결')}\n"
        f"{label} · {dim(st)}"
    )


def order_label(desc: str) -> str:
    """주문 설명 → 짧은 라벨 (plan_formatter와 유사)."""
    if desc.startswith("별 +") or "별지점" in desc:
        plus = desc.find("+")
        pct_end = desc.find("%", plus)
        if plus >= 0 and pct_end > plus:
            return f"별 {desc[plus:pct_end + 1]}"
    if "평단" in desc and "별" not in desc:
        return "평단"
    if "큰수" in desc or "첫 진입" in desc:
        return "큰수매수"
    if "하단 방어" in desc:
        for drop in (20, 30):
            if f"-{drop}%" in desc:
                return f"하단방어 −{drop}%"
    if "쿼터" in desc:
        return "쿼터 매도"
    if "익절" in desc:
        return "익절"
    if "리버스" in desc and "매수" in desc:
        return "리버스 매수"
    return desc.split("(")[0].strip()[:16]
