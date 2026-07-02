"""Format /plan — today's order plan."""

import datetime
from zoneinfo import ZoneInfo

from app import App
from tg.format_helpers import is_dry, resolve_price
from tg.ui import (
    THIN,
    code,
    dim,
    empty,
    mode_label,
    order_side,
    quote,
    section,
    symbol_card,
    usd,
)


def _order_formula(order: dict, plan: dict) -> str:
    """주문가 산정식 (plain text — blockquote 안 안전)."""
    action = order.get("action")
    price = float(order.get("price", 0))
    avg = float(plan.get("avg_price", 0))
    cur = float(plan.get("current_price", 0))
    star_pct = float(plan.get("star_pct", 0))
    star_price = float(plan.get("star_price", 0))
    star_buy = float(plan.get("star_buy", 0))
    premium = int(plan.get("premium_pct", 0))
    tp = float(plan.get("take_profit_pct", 0))
    desc = order.get("desc", "")

    if action == "BUY_FULL":
        if "큰수" in desc or "첫 진입" in desc:
            return f"현재가 ${cur:.2f} × (1+{premium}%) = ${price:.2f}"
        if "별지점" in desc or "후반전" in desc:
            return f"별가 ${star_price:.2f} − 0.01 = ${star_buy:.2f}"
        if "리버스" in desc and star_buy > 0:
            return f"별가 ${star_price:.2f} − 0.01 = ${star_buy:.2f}"
        if "강제1회" in desc:
            return desc.replace("강제1회 LOC (", "").rstrip(")")
    if action == "BUY_HALF":
        if "평단" in desc:
            return f"평단 ${avg:.2f}"
        if "별지점" in desc and star_buy > 0:
            return f"별가 ${star_price:.2f} − 0.01 = ${star_buy:.2f}"
        if "하단 방어" in desc:
            for drop in (10, 15, 20):
                if f"-{drop}%" in desc:
                    return f"현재가 ${cur:.2f} × (1−{drop}%) = ${price:.2f}"
    if action == "SELL_QUARTER":
        if avg > 0:
            return f"별가 = 평단 ${avg:.2f} × (1+{star_pct:g}%) = ${star_price:.2f}"
        return f"별가 ${star_price:.2f}"
    if action is None and "익절" in desc and avg > 0:
        return f"평단 ${avg:.2f} × (1+{tp:g}%) = ${price:.2f}"
    return ""


def _one_buy_formula(st: dict, plan: dict) -> str:
    principal = float(st["principal"])
    split = int(st["split_count"])
    t_val = float(st["T"])
    mode = plan.get("mode", "")
    safe_t = 0 if mode == "ENTRY" else min(t_val, split - 1)
    denom = split - safe_t
    if denom <= 0 or principal <= 0:
        return ""
    amt = plan.get("one_buy_amount", 0)
    return f"1회매수 = 원금 ${principal:,.0f} ÷ ({split} − {safe_t:g}) = ${amt:,.2f}"


def format_plan_block(app: App, symbol: str, premium: int) -> str:
    st = app.state.load(symbol)
    price = resolve_price(app, symbol)
    plan = app.strategy.get_plan(
        symbol, price, st["avg_price"], st["qty"], st["T"],
        premium, st["principal"], st["split_count"], st.get("force_one", False),
        take_profit_pct=st.get("take_profit_pct"),
    )
    strat = mode_label(plan["mode"])
    t_str = f"{st['T']:.2f}"
    star_pct = float(plan.get("star_pct", 0))
    star_price = float(plan.get("star_price", 0))
    tp_pct = float(plan.get("take_profit_pct", 0))
    avg = float(plan.get("avg_price", 0) or st["avg_price"])

    card = [
        symbol_card(symbol),
        f"🎯 {dim('T')} {code(t_str)}　│　"
        f"{dim('분할')} {code(str(st['split_count']))}　│　{strat}",
    ]

    if avg > 0 and star_price > 0:
        card.append(
            f"⭐ {dim('별%')} {code(f'+{star_pct:g}%')}　→　"
            f"{dim('별가')} {usd(star_price)}　"
            f"{dim(f'(평단 ${avg:.2f} × {1 + star_pct / 100:.4f})')}"
        )
        tp_price = round(avg * (1 + tp_pct / 100), 2)
        card.append(
            f"🎯 {dim('익절')} {code(f'+{tp_pct:g}%')}　→　"
            f"{usd(tp_price)}　"
            f"{dim(f'(평단 ${avg:.2f} × {1 + tp_pct / 100:.2f})')}"
        )
    elif star_pct != 0:
        card.append(f"⭐ {dim('별%')} {code(f'+{star_pct:g}%')}　{dim('(진입 후 별가 산출)')}")

    one_buy_line = _one_buy_formula(st, plan)
    if one_buy_line:
        card.append(f"💵 {dim(one_buy_line)}")

    orders = plan.get("buy_orders", []) + plan.get("sell_orders", [])
    if not orders:
        if price <= 0:
            hint = "LIVE 전환 후 표시" if is_dry(app) else "API 확인 필요"
            card.append(empty(f"주문 없음 · {hint}"))
        else:
            card.append(empty("주문 없음 · 조건 미충족"))
    else:
        card.append(THIN)
        for o in orders:
            icon, side = order_side(o["side"])
            card.append(f"{icon} <b>{side}</b>　{dim(o['desc'])}")
            card.append(f"　　{usd(o['price'])}　×　{code(str(o['qty']) + '주')}")
            formula = _order_formula(o, plan)
            if formula:
                card.append(f"　　{dim('└ ' + formula)}")

    return quote(*card)


def format_plans(app: App, symbols: list[str], premium: int) -> str:
    kst = ZoneInfo("Asia/Seoul")
    today = datetime.datetime.now(kst).strftime("%Y-%m-%d")
    blocks = [
        section("오늘 주문계획", "📋"),
        dim(f"{today} KST"),
        "",
    ]
    if not symbols:
        blocks.append(quote(empty("거래 종목이 없어요 · /setting → 📡 거래 종목")))
        return "\n".join(blocks)
    cards = [format_plan_block(app, symbol, premium) for symbol in symbols]
    blocks.append("\n\n".join(cards))
    return "\n".join(blocks)
