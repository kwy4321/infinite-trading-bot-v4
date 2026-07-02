"""Format /plan — today's order plan."""

import datetime
from zoneinfo import ZoneInfo

from app import App
from tg.format_helpers import is_dry, resolve_price
from tg.ui import (
    code,
    dim,
    empty,
    mode_label,
    quote,
    section,
    symbol_card,
    THIN,
)


def _short_label(desc: str) -> str:
    """주문 설명을 짧은 라벨로."""
    if desc.startswith("별 +") or "별지점" in desc or "후반전 별" in desc:
        plus = desc.find("+")
        pct_end = desc.find("%", plus)
        if plus >= 0 and pct_end > plus:
            return f"별 {desc[plus:pct_end + 1]}"
        return "별지점"
    if "평단" in desc and "별" not in desc:
        return "평단"
    if "큰수" in desc or "첫 진입" in desc:
        return "큰수매수"
    if "하단 방어" in desc or "방어" in desc:
        for drop in (20, 30):
            if f"-{drop}%" in desc:
                return f"하단방어 −{drop}%"
        return "하단방어"
    if "리버스 쿼터" in desc:
        return "리버스 쿼터"
    if "쿼터" in desc:
        return "쿼터 매도"
    if "익절" in desc:
        return "익절 매도"
    if "강제1회" in desc:
        return "강제1회"
    if "리버스" in desc and "매수" in desc:
        return "리버스 매수"
    return desc.split("(")[0].strip()[:12]


def _order_formula(order: dict, plan: dict) -> str:
    action = order.get("action")
    price = float(order.get("price", 0))
    avg = float(plan.get("avg_price", 0))
    cur = float(plan.get("current_price", 0))
    star_pct = float(plan.get("star_pct", 0))
    star_price = float(plan.get("star_price", 0))
    star_buy = float(plan.get("star_buy", 0))
    premium = int(plan.get("premium_pct", 0))
    tp = float(plan.get("take_profit_pct", 0))

    if action == "BUY_FULL":
        label = _short_label(order.get("desc", ""))
        if label == "큰수매수":
            return f"현재가 ${cur:.2f} × (1+{premium}%)"
        if label in ("별지점", "리버스 매수"):
            return f"별가 ${star_price:.2f} − 0.01"
    if action == "BUY_HALF":
        label = _short_label(order.get("desc", ""))
        if label == "평단":
            return f"평단 ${avg:.2f}"
        if label.startswith("별 +") or label == "별지점":
            return f"평단 ${avg:.2f} × (1+{star_pct:g}%)"
        if label.startswith("하단방어"):
            drop = label.replace("하단방어 −", "").replace("%", "")
            base = avg if avg > 0 else cur
            return f"평단 ${base:.2f} × (1−{drop}%)"
    if action == "SELL_QUARTER" and avg > 0:
        return f"평단 ${avg:.2f} × (1+{star_pct:g}%)"
    if action is None and "익절" in order.get("desc", "") and avg > 0:
        return f"평단 ${avg:.2f} × (1+{tp:g}%)"
    return ""


def _order_est_usd(order: dict) -> float:
    return round(float(order.get("price", 0)) * int(order.get("qty", 0)), 2)


def _format_order_lines(orders: list[dict], plan: dict, side: str) -> list[str]:
    if not orders:
        return []
    icon = "🟢" if side == "BUY" else "🔴"
    title = "매수" if side == "BUY" else "매도"
    total = sum(_order_est_usd(o) for o in orders)
    lines = [
        "",
        f"{icon} {title} {len(orders)}건  ·  {dim('합계')} {code(f'${total:,.2f}')}",
    ]
    for idx, o in enumerate(orders, 1):
        label = _short_label(o.get("desc", ""))
        price = float(o.get("price", 0))
        qty = int(o.get("qty", 0))
        est = _order_est_usd(o)
        if idx > 1:
            lines.append(THIN)
        lines.append(f"{idx}. {label}")
        lines.append(
            f"   💵 {code(f'${est:,.2f}')}  ·  "
            f"{dim(f'${price:.2f} × {qty}주')}"
        )
        formula = _order_formula(o, plan)
        if formula:
            lines.append(f"   {dim('기준')} {formula}")
    return lines


def format_plan_block(app: App, symbol: str, premium: int) -> str:
    st = app.state.load(symbol)
    price = resolve_price(app, symbol)
    plan = app.strategy.get_plan(
        symbol, price, st["avg_price"], st["qty"], st["T"],
        premium, st["principal"], st["split_count"], st.get("force_one", False),
        take_profit_pct=st.get("take_profit_pct"),
    )
    strat = mode_label(plan["mode"])
    star_pct = float(plan.get("star_pct", 0))
    star_price = float(plan.get("star_price", 0))
    tp_pct = float(plan.get("take_profit_pct", 0))
    avg = float(plan.get("avg_price", 0) or st["avg_price"])
    one_buy = float(plan.get("one_buy_amount", 0))

    card = [
        symbol_card(symbol),
        "",
        "📌 진행",
        f"T {st['T']:.2f}  ·  {st['split_count']}분할  ·  {strat}",
    ]

    if price > 0:
        if st["qty"] > 0 and avg > 0:
            card.append(f"현재 ${price:.2f}  ·  보유 {st['qty']}주 @ ${avg:.2f}")
        else:
            card.append(f"현재 ${price:.2f}  ·  보유 없음")
    elif is_dry(app):
        card.append("현재가 —  (LIVE 전환 후 표시)")

    card.extend(["", "📐 기준가"])
    if avg > 0 and star_price > 0:
        card.append(f"별% +{star_pct:g}%  →  ${star_price:.2f}")
        tp_price = round(avg * (1 + tp_pct / 100), 2)
        card.append(f"익절 +{tp_pct:g}%  →  ${tp_price:.2f}")
    elif star_pct != 0:
        card.append(f"별% +{star_pct:g}%  (진입 후 산출)")
    if one_buy > 0:
        card.append(f"1회 매수액  →  ${one_buy:,.2f}")

    buys = plan.get("buy_orders", [])
    sells = plan.get("sell_orders", [])
    if not buys and not sells:
        if price <= 0 and not is_dry(app):
            card.append("")
            card.append("📭 API 확인 필요")
        elif price > 0:
            card.append("")
            card.append("📭 오늘 주문 없음")
    else:
        card.extend(_format_order_lines(buys, plan, "BUY"))
        card.extend(_format_order_lines(sells, plan, "SELL"))

    return quote(*card)


def format_plans(app: App, symbols: list[str], premium: int) -> str:
    kst = ZoneInfo("Asia/Seoul")
    today = datetime.datetime.now(kst).strftime("%Y-%m-%d")
    blocks = [
        section("오늘 주문계획", "📋"),
        dim(today),
        "",
    ]
    if not symbols:
        blocks.append(quote(empty("거래 종목 없음 · /setting → 📡 거래 종목")))
        return "\n".join(blocks)
    cards = [format_plan_block(app, symbol, premium) for symbol in symbols]
    blocks.append("\n\n".join(cards))
    return "\n".join(blocks)
