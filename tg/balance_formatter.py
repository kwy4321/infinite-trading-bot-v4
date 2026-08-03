"""Format /balance — account snapshot (계좌현황).

계좌 숫자는 services.account_service 가 유일한 출처다. 여기서는 표시만 한다.
"""

from __future__ import annotations

from app import App
from services.account_service import AccountSnapshot, Holding, fetch_account_snapshot
from tg.ui import (
    THIN,
    code,
    empty,
    krw,
    quote,
    row,
    section,
    subsection,
    symbol_card,
    usd,
)


def _summary_rows(acct: AccountSnapshot) -> list[str]:
    rows = [row("🇺🇸", "총 자산", usd(acct.total_usd))]
    total_krw = acct.total_krw_or_converted()
    if total_krw > 0:
        rows.append(row("🇰🇷", "총 자산", krw(total_krw)))
    if acct.cash_krw > 0:
        rows.append(
            row("💵", "예수금", f"{usd(acct.cash_usd)}  ·  {krw(acct.cash_krw)}"),
        )
    else:
        rows.append(row("💵", "예수금", usd(acct.cash_usd)))
    if acct.fx_rate > 0:
        rows.append(row("💱", "환율", code(f"$1 = ₩{acct.fx_rate:,.2f}")))
    return rows


def _holding_rows(holding: Holding | dict) -> list[str]:
    """보유 1종목 표시. dict 도 받아 기존 호출부·테스트와 호환한다."""
    if isinstance(holding, dict):
        from core.money import holding_avg_price, holding_market_value, parse_money

        sym = str(holding.get("symbol", "?")).upper()
        qty = parse_money(holding.get("quantity"))
        avg = holding_avg_price(holding)
        mkt_usd = holding_market_value(holding, "usd")
        mkt_krw = holding_market_value(holding, "krw")
    else:
        sym = holding.symbol
        qty = holding.qty
        avg = holding.avg_price
        mkt_usd = holding.market_value_usd
        mkt_krw = holding.market_value_krw

    eval_row = row("💰", "평가", usd(mkt_usd))
    if mkt_krw > 0:
        eval_row = row("💰", "평가", f"{usd(mkt_usd)}  ·  {krw(mkt_krw)}")

    return [
        symbol_card(sym),
        row("📊", "수량", code(f"{qty:g}주")),
        row("📐", "평단", usd(avg)),
        eval_row,
    ]


def format_balance(app: App) -> str:
    acct = fetch_account_snapshot(app)
    lines = [section("계좌현황", "💼"), ""]

    if acct.dry:
        lines.append(empty("🧪 DRY 모드 — Toss API 미조회"))
        return "\n".join(lines)
    if not acct.ok:
        lines.append(empty("계좌 조회 실패 — /token 으로 API 상태 확인"))
        return "\n".join(lines)

    lines.extend([subsection("요약"), quote(*_summary_rows(acct)), ""])

    display = acct.tracked(app.runtime.active_symbols())
    if display:
        rows: list[str] = []
        for i, holding in enumerate(display):
            if i > 0:
                rows.append(THIN)
            rows.extend(_holding_rows(holding))
        lines.append(subsection("보유 종목"))
        lines.append(quote(*rows))
    else:
        lines.append(empty("보유 종목 없음"))

    return "\n".join(lines)
