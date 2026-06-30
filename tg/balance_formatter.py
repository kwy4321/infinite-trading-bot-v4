"""Format /balance — account snapshot (계좌현황)."""

from broker.toss_client import _money
from app import App
from config.settings import SYMBOLS
from tg.ui import section


def format_balance(app: App) -> str:
    broker = app.broker
    lines = [section("계좌현황", "💼"), ""]

    buying = broker.get_buying_power("USD")
    cash = float(buying.get("cashBuyingPower", 0) or 0) if buying else 0.0
    lines.append(f"💵 예수금  <b>${cash:,.2f}</b>")
    lines.append("")

    overview = broker.get_holdings_overview() or {}
    items = overview.get("items", [])
    tracked = [i for i in items if i.get("symbol", "").upper() in SYMBOLS]
    display = tracked or items

    if display:
        for item in display:
            lines.append(_holding_row(item))
            lines.append("")
    else:
        lines.append("📭 보유 종목 없음")

    if lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def _holding_row(item: dict) -> str:
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

    label = sym if name.upper() == sym else f"{sym}  {name}"
    return (
        f"📦 <b>{label}</b>\n"
        f"📊 {qty:g}주  │  평단 ${avg:.2f}  │  💰 ${mkt:,.2f}"
    )
