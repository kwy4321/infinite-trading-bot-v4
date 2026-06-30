"""Format /dashboard — records asset dashboard (자산·손익·환율·실현수익)."""

from broker.toss_client import _money, _pct
from app import App
from config.settings import SYMBOLS
from tg.format_helpers import is_dry, resolve_price
from tg.ui import (
    DIVIDER,
    code,
    dim,
    krw,
    pnl_dot,
    pnl_line,
    pnl_line_precise,
    row,
    section,
    subsection,
    symbol_card,
    usd,
)


def _cash_amount(buying: dict) -> float:
    if not buying:
        return 0.0
    raw = buying.get("cashBuyingPower", buying.get("cash", buying))
    return _money(raw, "usd") if isinstance(raw, dict) else float(raw or 0)


def _cash_krw(buying: dict) -> float:
    if not buying:
        return 0.0
    raw = buying.get("cashBuyingPower", buying.get("cash", buying))
    return _money(raw, "krw")


def _item_unrealized(item: dict) -> tuple[float, float | None]:
    for key in ("evaluationProfitLoss", "profitLoss", "profit", "unrealizedProfitLoss"):
        val = item.get(key)
        if val is None:
            continue
        u = _money(val, "usd")
        p = _pct(val)
        if u != 0 or p is not None:
            return u, p
    qty = float(item.get("quantity", 0) or 0)
    avg = float(item.get("averagePurchasePrice", 0) or 0)
    if avg == 0:
        cost = item.get("cost", {})
        avg = float(cost.get("averagePrice", 0) or 0)
    last = float(item.get("lastPrice", 0) or 0)
    if qty > 0 and avg > 0 and last > 0:
        u = round((last - avg) * qty, 2)
        p = round((last - avg) / avg * 100, 2)
        return u, p
    return 0.0, None


def _fetch_account(app: App) -> dict:
    broker = app.broker
    overview = broker.get_holdings_overview() or {}
    items = overview.get("items", [])
    tracked = [i for i in items if i.get("symbol", "").upper() in SYMBOLS]
    display = tracked or items

    buying_usd = broker.get_buying_power("USD")
    buying_krw = broker.get_buying_power("KRW")
    cash_usd = _cash_amount(buying_usd)
    cash_krw = _cash_krw(buying_krw)

    stock_usd = sum(_money(i.get("marketValue"), "usd") for i in display)
    unreal_usd = 0.0
    cost_usd = 0.0
    for item in display:
        u, _ = _item_unrealized(item)
        unreal_usd += u
        qty = float(item.get("quantity", 0) or 0)
        avg = float(item.get("averagePurchasePrice", 0) or 0)
        if avg == 0:
            cost = item.get("cost", {})
            avg = float(cost.get("averagePrice", 0) or 0)
        cost_usd += qty * avg

    total_usd = _money(overview.get("totalEvaluationAmount"), "usd")
    total_krw = _money(overview.get("totalEvaluationAmount"), "krw")
    if total_usd <= 0:
        total_usd = cash_usd + stock_usd
    if total_krw <= 0 and cash_krw > 0:
        total_krw = cash_krw + sum(_money(i.get("marketValue"), "krw") for i in display)

    fx = broker.get_exchange_rate("USD", "KRW")
    fx_rate = float(fx.get("rate") or fx.get("midRate") or 0)
    unreal_pct = round(unreal_usd / cost_usd * 100, 2) if cost_usd > 0 else None

    return {
        "cash_usd": cash_usd,
        "total_usd": total_usd,
        "total_krw": total_krw,
        "unreal_usd": round(unreal_usd, 2),
        "unreal_pct": unreal_pct,
        "fx_rate": fx_rate,
    }


def _active_cycle_lines(app: App) -> list[str]:
    lines = []
    for sym in SYMBOLS:
        st = app.state.load(sym)
        price = resolve_price(app, sym)
        live = app.cycles.calc_unrealized_pnl(sym, st["qty"], st["avg_price"], price)
        if not live:
            continue
        lines.append(
            f"   {symbol_card(sym)}  #{code(str(live['cycle_no']))}  "
            f"{pnl_line(live['cycle_pnl_usd'], live['cycle_pnl_pct'])}"
        )
    return lines


def _realized_block(stats: dict, cash_usd: float) -> list[str]:
    realized = stats["realized_usd"]
    completed = stats["completed_cycles"]
    active = stats["active_cycles"]
    pct_val = round(realized / cash_usd * 100, 2) if cash_usd > 0 else None

    lines = [
        subsection("🏦 무한매수 실현 수익"),
        row("📊", "회차", f"{dim('완료')} {code(str(completed))}  │  {dim('진행')} {code(str(active))}"),
    ]
    if pct_val is not None:
        lines.append(f"   {pnl_line_precise(realized, pct_val)}")
        sign = "+" if pct_val >= 0 else ""
        lines.append(f"   {dim('예수금 대비')}  {code(f'{sign}{pct_val:.2f}%')}")
    else:
        sign = "+" if realized >= 0 else ""
        lines.append(f"   {pnl_dot(realized >= 0)} {code(f'{sign}${realized:,.2f}')}")
        if cash_usd <= 0:
            lines.append(f"   {dim('예수금 대비')}  —")
    return lines


def format_records_dashboard(app: App) -> str:
    stats = app.cycles.portfolio_stats()
    lines = [section("자산 대시보드", "📒"), ""]

    if is_dry(app):
        lines.append(dim("🧪 DRY 모드 — Toss API 미조회"))
        lines.extend(["", *_realized_block(stats, 0.0)])
        active = _active_cycle_lines(app)
        if active:
            lines.extend(["", subsection("진행 회차 (평가)"), *active])
        return "\n".join(lines)

    acct = _fetch_account(app)
    fx_rate = acct["fx_rate"]
    unreal_krw = acct["unreal_usd"] * fx_rate if fx_rate > 0 else 0.0
    total_krw = acct["total_krw"]
    if total_krw <= 0 and fx_rate > 0:
        total_krw = acct["total_usd"] * fx_rate

    lines.extend([
        subsection("💰 총 자산"),
        f"   {row('🇺🇸', 'USD', usd(acct['total_usd']))}",
    ])
    if total_krw > 0:
        lines.append(f"   {row('🇰🇷', 'KRW', krw(total_krw))}")
    lines.extend([
        "",
        row("💵", "예수금", usd(acct["cash_usd"])),
        "",
        subsection("📈 미실현 손익"),
    ])

    if acct["unreal_pct"] is not None:
        lines.append(f"   {pnl_line_precise(acct['unreal_usd'], acct['unreal_pct'])}")
    else:
        sign = "+" if acct["unreal_usd"] >= 0 else ""
        lines.append(f"   {pnl_dot(acct['unreal_usd'] >= 0)} {code(f'{sign}${acct['unreal_usd']:,.2f}')}")

    if fx_rate > 0:
        sign = "+" if unreal_krw >= 0 else ""
        lines.append(f"   {row('🇰🇷', 'KRW', code(f'{sign}₩{unreal_krw:,.0f}'))}")
        lines.append("")
        lines.append(row("💱", "환율", code(f"$1 = ₩{fx_rate:,.2f}")))
    else:
        lines.extend(["", row("💱", "환율", dim("조회 실패"))])

    lines.extend(["", DIVIDER, ""])
    lines.extend(_realized_block(stats, acct["cash_usd"]))

    active = _active_cycle_lines(app)
    if active:
        lines.extend(["", subsection("진행 회차 (평가)"), *active])

    per_sym = stats.get("per_symbol", {})
    detail = [
        sym for sym in SYMBOLS
        if per_sym.get(sym, {}).get("realized_usd", 0) != 0 or per_sym.get(sym, {}).get("active")
    ]
    if detail:
        lines.extend(["", subsection("종목별 실현")])
        for sym in detail:
            info = per_sym[sym]
            sign = "+" if info["realized_usd"] >= 0 else ""
            tag = dim(" · 진행 중") if info.get("active") else ""
            lines.append(
                f"   {symbol_card(sym)}  {code(f'{sign}${info['realized_usd']:,.0f}')}"
                f"  {dim('(' + str(info['completed_cycles']) + '회)')}{tag}"
            )

    return "\n".join(lines)
