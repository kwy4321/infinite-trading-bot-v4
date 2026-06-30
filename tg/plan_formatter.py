"""Format /plan — today's order plan."""

import datetime
from zoneinfo import ZoneInfo

from app import App


def format_plan_block(app: App, symbol: str, premium: int) -> str:
    st = app.state.load(symbol)
    pos = app.broker.get_holdings_item(symbol)
    plan = app.strategy.get_plan(
        symbol, pos["current_price"], st["avg_price"], st["qty"], st["T"],
        premium, st["cash"], st["split_count"], st["principal"],
    )

    lines = [
        f"<b>{symbol}</b>  T {st['T']:.2f} · {st['split_count']}분할 · {plan['mode']}",
        f"1회 매수 ${plan['one_buy_amount']:,.2f}",
        "",
    ]

    orders = plan.get("buy_orders", []) + plan.get("sell_orders", [])
    if not orders:
        lines.append("  주문 없음")
    else:
        for o in orders:
            side = "매수" if o["side"] == "BUY" else "매도"
            lines.append(f"  {side}  {o['desc']}")
            lines.append(f"       ${o['price']:.2f} × {o['qty']}주")

    return "\n".join(lines)


def format_plans(app: App, symbols: list[str], premium: int) -> str:
    kst = ZoneInfo("Asia/Seoul")
    today = datetime.datetime.now(kst).strftime("%Y-%m-%d")
    blocks = [f"📋 <b>오늘의 주문계획</b>  {today}  (+{premium}%)", ""]
    for i, symbol in enumerate(symbols):
        if i > 0:
            blocks.append("")
        blocks.append(format_plan_block(app, symbol, premium))
    return "\n".join(blocks)
