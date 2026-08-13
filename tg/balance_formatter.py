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
    total_krw = acct.total_krw_or_converted()
    rows = [row("💼", "총 자산", krw(total_krw))]

    rows.append(row("💵", "달러", usd(acct.cash_usd)))
    if acct.cash_krw > 0:
        rows.append(row("🇰🇷", "원화", krw(acct.cash_krw)))

    stock_val = usd(acct.stock_usd)
    if acct.stock_krw > 0:
        stock_val = f"{usd(acct.stock_usd)}  ·  {krw(acct.stock_krw)}"
    elif acct.fx_rate > 0 and acct.stock_usd > 0:
        stock_val = f"{usd(acct.stock_usd)}  ·  {krw(acct.stock_usd * acct.fx_rate)}"
    rows.append(row("📊", "주식 보유", stock_val))

    if acct.fx_rate > 0:
        rows.append(row("💱", "환율", code(f"$1 = ₩{acct.fx_rate:,.2f}")))
    return rows


def _pct_display(pct_val: float | None) -> str:
    if pct_val is None:
        return "—"
    sign = "+" if pct_val > 0 else ""
    return code(f"{sign}{pct_val:.2f}%")


def _holding_rows(holding: Holding | dict) -> list[str]:
    """보유 1종목 표시. dict 도 받아 기존 호출부·테스트와 호환한다."""
    if isinstance(holding, dict):
        from core.money import (
            holding_avg_price,
            holding_close_value_krw,
            holding_close_value_usd,
            holding_unrealized,
            parse_money,
        )

        sym = str(holding.get("symbol", "?")).upper()
        qty = parse_money(holding.get("quantity"))
        avg = holding_avg_price(holding)
        mkt_usd = holding_close_value_usd(holding)
        mkt_krw = holding_close_value_krw(holding, fx=0.0)
        cost_usd = round(qty * avg, 2) if qty > 0 and avg > 0 else 0.0
        _, unreal_pct = holding_unrealized(holding)
        if unreal_pct is None and cost_usd > 0:
            unreal_pct = round((mkt_usd - cost_usd) / cost_usd * 100, 2)
    else:
        sym = holding.symbol
        mkt_usd = holding.market_value_usd
        mkt_krw = holding.market_value_krw
        cost_usd = holding.cost_usd
        unreal_pct = holding.unrealized_pct
        if unreal_pct is None and cost_usd > 0:
            unreal_pct = round((mkt_usd - cost_usd) / cost_usd * 100, 2)

    eval_row = row("💰", "평가금액", usd(mkt_usd))
    if mkt_krw > 0:
        eval_row = row("💰", "평가금액", f"{usd(mkt_usd)}  ·  {krw(mkt_krw)}")

    return [
        symbol_card(sym),
        row("🛒", "매입금액", usd(cost_usd)),
        eval_row,
        row("📈", "수익률", _pct_display(unreal_pct)),
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
