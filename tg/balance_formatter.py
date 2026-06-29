"""Toss account balance for /balance."""

from broker.toss_client import _money, _pct
from app import App
from config.settings import SYMBOLS


def format_balance(app: App) -> str:
    broker = app.broker
    seq = app.settings.toss_account_seq
    lines = [f"💼 <b>Toss 계좌 잔고</b> (계좌 #{seq})\n"]

    buying = broker.get_buying_power("USD")
    cash_power = float(buying.get("cashBuyingPower", 0) or 0)
    if cash_power:
        lines.append(f"💵 매수 가능 (USD): ${cash_power:,.2f}")

    overview = broker.get_holdings_overview() or {}
    purchase = _money(overview.get("totalPurchaseAmount"), "usd")
    market = _money(overview.get("marketValue"), "usd")
    pnl = _money(overview.get("profitLoss"), "usd")
    pnl_pct = _pct(overview.get("profitLoss"))

    if market or purchase:
        lines.append(f"📊 평가금액 (USD): ${market:,.2f}")
        lines.append(f"📉 매입금액 (USD): ${purchase:,.2f}")
        if pnl or pnl_pct is not None:
            sign = "+" if pnl >= 0 else ""
            pct_txt = f" ({sign}{pnl_pct:.2f}%)" if pnl_pct is not None else ""
            lines.append(f"📈 평가손익: {sign}${pnl:,.2f}{pct_txt}")

    items = overview.get("items", [])
    tracked = [i for i in items if i.get("symbol", "").upper() in SYMBOLS]
    others = [i for i in items if i.get("symbol", "").upper() not in SYMBOLS]

    if tracked:
        lines.append("\n<b>보유 (TQQQ / SOXL)</b>")
        for item in tracked:
            lines.append(_format_holding_line(item))

    if others:
        lines.append("\n<b>기타 보유</b>")
        for item in others:
            lines.append(_format_holding_line(item))

    if not items and not cash_power:
        lines.append("\n보유 종목 없음")

    return "\n".join(lines)


def _format_holding_line(item: dict) -> str:
    sym = item.get("symbol", "?").upper()
    name = item.get("name", sym)
    qty = float(item.get("quantity", 0) or 0)
    avg = float(item.get("averagePurchasePrice", 0) or 0)
    if avg == 0:
        cost = item.get("cost", {})
        avg = float(cost.get("averagePrice", 0) or 0)
    last = float(item.get("lastPrice", 0) or 0)
    mkt = _money(item.get("marketValue"), "usd")
    if mkt == 0 and qty and last:
        mkt = qty * last
    pnl_pct = _pct(item.get("profitLoss"))
    pct_txt = ""
    if pnl_pct is not None:
        sign = "+" if pnl_pct >= 0 else ""
        pct_txt = f" ({sign}{pnl_pct:.1f}%)"
    return (
        f"• <b>{sym}</b> {name}\n"
        f"  {qty:g}주 @ ${avg:.2f} | 평가 ${mkt:,.2f}{pct_txt}"
    )
