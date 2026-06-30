"""Format /plan — today's order plan."""

import datetime
from zoneinfo import ZoneInfo

from app import App
from tg.format_helpers import is_dry, resolve_price
from tg.ui import (
    DIVIDER,
    code,
    dim,
    empty,
    mode_label,
    order_side,
    row,
    section,
    symbol_card,
    usd,
)


def format_plan_block(app: App, symbol: str, premium: int) -> str:
    st = app.state.load(symbol)
    price = resolve_price(app, symbol)
    plan = app.strategy.get_plan(
        symbol, price, st["avg_price"], st["qty"], st["T"],
        premium, st["principal"], st["split_count"], st.get("force_one", False),
    )
    strat = mode_label(plan["mode"])

    lines = [
        symbol_card(symbol),
        f"   🎯 {dim('T')} {code(f'{st['T']:.2f}')}  "
        f"│  {dim('분할')} {code(str(st['split_count']))}  │  {strat}",
        f"   💵 {dim('1회 매수')}  {usd(plan['one_buy_amount'])}",
        "",
    ]

    orders = plan.get("buy_orders", []) + plan.get("sell_orders", [])
    if not orders:
        if price <= 0:
            hint = "LIVE 전환 후 표시" if is_dry(app) else "API 확인 필요"
            lines.append(empty(f"주문 없음 · {hint}"))
        else:
            lines.append(empty("주문 없음 · 조건 미충족"))
    else:
        for o in orders:
            icon, side = order_side(o["side"])
            lines.append(f"   {icon} <b>{side}</b>  {o['desc']}")
            lines.append(f"      {usd(o['price'])}  ×  {code(str(o['qty']) + '주')}")

    return "\n".join(lines)


def format_plans(app: App, symbols: list[str], premium: int) -> str:
    if not symbols:
        symbols = list(app.runtime.active_symbols()) or list(app.state.list_symbols())
    kst = ZoneInfo("Asia/Seoul")
    today = datetime.datetime.now(kst).strftime("%Y-%m-%d")
    blocks = [
        section("오늘 주문계획", "📋"),
        row("📅", today, f"{dim('큰수매수')} {code(f'+{premium}%')}"),
        "",
    ]
    for i, symbol in enumerate(symbols):
        if i > 0:
            blocks.extend([DIVIDER, ""])
        blocks.append(format_plan_block(app, symbol, premium))
    return "\n".join(blocks)
