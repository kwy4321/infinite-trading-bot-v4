"""Format /plan — today's order plan."""

from __future__ import annotations

from app import App
from broker.toss_client import TossClient
from core.clock import loc_auto_submit_kst, now_kst
from services.market_data import resolve_price, resolve_prices
from services.trading_context import (
    is_dry,
    resolve_available_cash,
    sync_broker_dry_run,
)
from render.labels import short_order_label
from strategy.session_fill import has_us_session_fill_in_state
from tg.ui import (
    card,
    code,
    dim,
    empty,
    esc,
    mode_label,
    section,
    side_icon,
    symbol_card,
    THIN,
)


def _short_label(desc: str) -> str:
    """주문 설명을 짧은 라벨로 (구현은 render.labels 공용)."""
    return short_order_label(desc, style="plan")


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
        if label in ("별지점", "리버스 별매수", "리버스 매수", "리버스 쿼터매수"):
            return f"별 ${star_price:.2f} − 0.01 (쿼터매수)"
    if action == "REVERSE_BUY":
        qb = float(plan.get("quarter_buy_budget", 0))
        return f"잔금÷4 ${qb:,.0f} · 별 ${star_price:.2f} 아래"
    if action in ("REVERSE_SELL", "REVERSE_SELL_FIRST"):
        return f"5일 종가 평균(별) ${star_price:.2f}"
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
    icon = side_icon(side)
    title = "매수" if side == "BUY" else "매도"
    total = sum(_order_est_usd(o) for o in orders)
    lines = [
        "",
        f"{icon} {title} {len(orders)}건  ·  {dim('LOC')}  ·  {dim('합계')} {code(f'${total:,.2f}')}",
    ]
    for idx, o in enumerate(orders, 1):
        label = _short_label(o.get("desc", ""))
        price = float(o.get("price", 0))
        qty = int(o.get("qty", 0))
        est = _order_est_usd(o)
        if idx > 1:
            lines.append(THIN)
        lines.append(f"{idx}. {esc(label)}")
        lines.append(
            f"   💵 {code(f'${est:,.2f}')}  ·  "
            f"{dim(f'${price:.2f} × {qty}주')}"
        )
        formula = _order_formula(o, plan)
        if formula:
            lines.append(f"   {dim('기준')} {formula}")
    return lines


def format_plan_block(
    app: App, symbol: str, premium: int, *, price: float | None = None,
) -> str:
    st = app.state.load(symbol)
    if price is None:
        price = resolve_price(app, symbol)
    cash = resolve_available_cash(app, symbol, st)
    plan = app.strategy.get_plan_from_state(
        symbol, price, st, premium, available_cash=cash,
    )
    app.state.save(symbol, st)
    strat = mode_label(plan["mode"])
    star_pct = float(plan.get("star_pct", 0))
    star_price = float(plan.get("star_price", 0))
    tp_pct = float(plan.get("take_profit_pct", 0))
    avg = float(plan.get("avg_price", 0) or st["avg_price"])
    one_buy = float(plan.get("one_buy_amount", 0))
    is_reverse = bool(plan.get("reverse_mode"))

    card_lines = [
        symbol_card(symbol),
        "",
        "📌 진행",
        f"🎯 T {st['T']:.2f}  ·  🍰 {st['split_count']}분할  ·  {strat}",
    ]

    if price > 0:
        if st["qty"] > 0 and avg > 0:
            card_lines.append(f"현재 ${price:.2f}  ·  보유 {st['qty']}주 @ ${avg:.2f}")
        else:
            card_lines.append(f"현재 ${price:.2f}  ·  보유 없음")
    elif is_dry(app):
        card_lines.append("현재가 —  (LIVE 전환 후 표시)")

    card_lines.extend(["", "📐 기준가"])
    if is_reverse and star_price > 0:
        card_lines.append(f"별(5일 종가 평균)  →  ${star_price:.2f}")
        if plan.get("reverse_first_day"):
            card_lines.append(dim("첫날: MOC 무조건 매도 · 매수 없음"))
        else:
            qb = float(plan.get("quarter_buy_budget", 0))
            card_lines.append(f"쿼터매수(잔금÷4)  →  ${qb:,.2f}")
    elif avg > 0 and star_price > 0:
        card_lines.append(f"별% +{star_pct:g}%  →  ${star_price:.2f}")
        tp_price = round(avg * (1 + tp_pct / 100), 2)
        card_lines.append(f"익절 +{tp_pct:g}%  →  ${tp_price:.2f}")
    elif star_pct != 0:
        card_lines.append(f"별% +{star_pct:g}%  (진입 후 산출)")
    if one_buy > 0 and not is_reverse:
        card_lines.append(f"1회 매수액  →  ${one_buy:,.2f}")

    buys = plan.get("buy_orders", [])
    sells = plan.get("sell_orders", [])
    if not buys and not sells:
        if price <= 0 and not is_dry(app):
            card_lines.extend(["", "📭 API 확인 필요"])
        elif price > 0:
            card_lines.extend(["", "📭 오늘 주문 없음"])
    else:
        card_lines.extend(_format_order_lines(buys, plan, "BUY"))
        card_lines.extend(_format_order_lines(sells, plan, "SELL"))

    return card(*card_lines)


def format_plans(app: App, symbols: list[str], premium: int) -> str:
    sync_broker_dry_run(app)
    today = now_kst().strftime("%Y-%m-%d")
    us_close_date = TossClient.target_us_date_for_evening_loc()
    submit_kst = loc_auto_submit_kst(us_close_date)
    blocks = [
        section("오늘 주문계획", "📋"),
        dim(f"{today} KST · 미국 거래일 {us_close_date}"),
        dim("※ 종가 LOC · 18:00 계획 · 18:05 매수·매도 CLS 동시 접수 · 체결은 종가 경매"),
        "",
    ]
    if not symbols:
        blocks.append(empty("거래 종목 없음 · /setting → 거래 종목"))
        return "\n".join(blocks)
    skip_notes = []
    for symbol in symbols:
        st = app.state.load(symbol)
        if has_us_session_fill_in_state(
            st, symbol, us_close_date, app.cycles, submit_kst,
        ):
            skip_notes.append(
                f"⏭️ {symbol_card(symbol)} — {us_close_date} 18:05 이전 LOC 이미 접수됨 "
                f"(자동접수 스킵 · /run 으로 재시도 시에도 동일)"
            )
    prices = resolve_prices(app, symbols)
    cards = [
        format_plan_block(app, symbol, premium, price=prices.get(symbol.upper(), 0.0))
        for symbol in symbols
    ]
    blocks.append("\n\n".join(cards))
    blocks.append("")
    blocks.append(dim("🌙 종가 LOC — 조건 충족 시에만 체결 (미충족 시 미체결 · 새벽 sync 확인)"))
    if skip_notes:
        blocks.extend(skip_notes)
    return "\n".join(blocks)
