"""Telegram notification text — 장시작·장마감·주문 접수·체결."""

from __future__ import annotations

from render.labels import short_order_label
from tg.ui import bold, code, dim, esc, side_icon


def _side_ko(side: str) -> str:
    return "매수" if str(side).upper() == "BUY" else "매도"


def format_market_open(now_kst: str) -> str:
    return (
        f"🔔 {bold('미국 프리마켓')}  {dim(f'{now_kst} KST')}\n"
        f"{dim('18:00 계획 · 18:05 매수·매도 CLS 동시 접수. 체결은 종가 경매·새벽 sync 반영.')}"
    )


def format_market_open_start(now_kst: str, symbol_count: int) -> str:
    sym = f"{symbol_count}종목" if symbol_count else "—"
    return (
        f"🔔 {bold('프리장 LOC 접수')}  {dim(f'{now_kst} KST')}\n"
        f"CLS 주문 접수 · {code(sym)}"
    )


def format_market_open_report(
    now_kst: str,
    symbol_lines: list[str],
    ok: int,
    total: int,
) -> str:
    """프리마켓 LOC — 종목별 접수 결과."""
    header = f"🔔 {bold('프리마켓 LOC 접수 완료')}  {dim(now_kst)}"
    if total <= 0:
        return f"{header}\n{dim('오늘 예약할 주문 없음')}"
    body = "\n".join(symbol_lines)
    footer = f"접수 {code(str(ok))}/{code(str(total))}건 · {dim('체결은 종가 후 job4/sync 반영')}"
    return f"{header}\n\n{body}\n\n{footer}"


def format_market_close_start(now_kst: str, symbol_count: int) -> str:
    sym = f"{symbol_count}종목" if symbol_count else "—"
    return (
        f"🔔 {bold('미국 장 마감')}  {dim(f'{now_kst} KST')}\n"
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
    header = f"🔔 {bold('장 마감 완료')}  {dim(now_kst)}"
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
        f"📥 {bold(symbol)} {_side_ko(side)} {bold('접수')}{tag}{kind}\n"
        f"{side_icon(side)} {esc(label)} · {code(f'{qty}주')}{oid}"
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
        f"✅ {bold(symbol)} {_side_ko(side)} {bold('체결')}{tag}\n"
        f"{side_icon(side)} {esc(label)} · {code(f'{qty:g}주')} @ {price_txt}"
    )


def format_order_not_filled(
    symbol: str,
    side: str,
    label: str,
    status: str,
) -> str:
    st = status or "미체결"
    return (
        f"⚠️ {bold(symbol)} {_side_ko(side)} {dim('미체결')}\n"
        f"{esc(label)} · {dim(st)}"
    )


def order_label(desc: str) -> str:
    """주문 설명 → 짧은 라벨 (구현은 render.labels 공용)."""
    return short_order_label(desc, style="notify")
