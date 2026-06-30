"""Format /balance — account snapshot (계좌현황)."""

from broker.toss_client import _money
from app import App
from config.settings import SYMBOLS
from tg.ui import THIN, code, dim, empty, quote, row, section, symbol_card, usd


def format_balance(app: App) -> str:
    broker = app.broker
    lines = [section("계좌현황", "💼"), ""]

    buying = broker.get_buying_power("USD")
    cash = float(buying.get("cashBuyingPower", 0) or 0) if buying else 0.0
    lines.append(quote(row("💵", "예수금", usd(cash))))
    lines.append("")

    overview = broker.get_holdings_overview() or {}
    items = overview.get("items", [])
    tracked = [i for i in items if i.get("symbol", "").upper() in SYMBOLS]
    display = tracked or items

    if display:
        rows = []
        for i, item in enumerate(display):
            if i > 0:
                rows.append(THIN)
            rows.extend(_holding_rows(item))
        lines.append(quote(*rows))
    else:
        lines.append(empty("보유 종목 없음"))

    return "\n".join(lines)


def _holding_rows(item: dict) -> list[str]:
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

    label = sym if name.upper() == sym else f"{sym} · {name}"
    return [
        symbol_card(label),
        f"📊 {code(f'{qty:g}주')}　│　{dim('평단')} {usd(avg)}　│　💰 {usd(mkt)}",
    ]
