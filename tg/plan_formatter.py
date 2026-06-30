"""Format /plan — today's order plan."""

import datetime
from zoneinfo import ZoneInfo

from app import App
from tg.format_helpers import is_dry, resolve_price
from tg.ui import DIVIDER, mode_label, section


def format_plan_block(app: App, symbol: str, premium: int) -> str:
    st = app.state.load(symbol)
    price = resolve_price(app, symbol)
    plan = app.strategy.get_plan(
        symbol, price, st["avg_price"], st["qty"], st["T"],
        premium, st["cash"], st["split_count"], st["principal"],
    )
    strat = mode_label(plan["mode"])

    lines = [
        f"📦 <b>{symbol}</b>",
        f"🎯 T {st['T']:.2f}  │  {st['split_count']}분할  │  {strat}",
        f"💵 1회 매수  ${plan['one_buy_amount']:,.2f}",
        "",
    ]

    orders = plan.get("buy_orders", []) + plan.get("sell_orders", [])
    if not orders:
        if price <= 0:
            hint = "🧪 LIVE 전환 후 표시" if is_dry(app) else "⚠️ API 확인 필요"
            lines.append(f"📭 주문 없음  ·  {hint}")
        else:
            lines.append("📭 주문 없음  ·  조건 미충족")
    else:
        for o in orders:
            icon = "🟢" if o["side"] == "BUY" else "🔴"
            side = "매수" if o["side"] == "BUY" else "매도"
            lines.append(f"{icon} {side}  {o['desc']}")
            lines.append(f"     ${o['price']:.2f}  ×  {o['qty']}주")

    return "\n".join(lines)


def format_plans(app: App, symbols: list[str], premium: int) -> str:
    if not symbols:
        symbols = list(app.runtime.active_symbols()) or list(app.state.list_symbols())
    kst = ZoneInfo("Asia/Seoul")
    today = datetime.datetime.now(kst).strftime("%Y-%m-%d")
    blocks = [
        section("오늘 주문계획", "📋"),
        f"📅 {today}  │  ➕ 할증 {premium}%",
        "",
    ]
    for i, symbol in enumerate(symbols):
        if i > 0:
            blocks.append(DIVIDER)
            blocks.append("")
        blocks.append(format_plan_block(app, symbol, premium))
    return "\n".join(blocks)
