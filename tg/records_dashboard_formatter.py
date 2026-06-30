"""Format /dashboard — records asset dashboard (자산·손익·환율·실현수익)."""

from broker.toss_client import _money, _pct
from app import App
from config.settings import SYMBOLS
from tg.format_helpers import is_dry, resolve_price
from tg.ui import DIVIDER, pnl_line, section


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
        usd = _money(val, "usd")
        pct = _pct(val)
        if usd != 0 or pct is not None:
            return usd, pct
    qty = float(item.get("quantity", 0) or 0)
    avg = float(item.get("averagePurchasePrice", 0) or 0)
    if avg == 0:
        cost = item.get("cost", {})
        avg = float(cost.get("averagePrice", 0) or 0)
    last = float(item.get("lastPrice", 0) or 0)
    if qty > 0 and avg > 0 and last > 0:
        usd = round((last - avg) * qty, 2)
        pct = round((last - avg) / avg * 100, 2)
        return usd, pct
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
        "cash_krw": cash_krw,
        "total_usd": total_usd,
        "total_krw": total_krw,
        "unreal_usd": round(unreal_usd, 2),
        "unreal_pct": unreal_pct,
        "fx_rate": fx_rate,
        "items": display,
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
            f"  📦 {sym} #{live['cycle_no']}회차  "
            f"{pnl_line(live['cycle_pnl_usd'], live['cycle_pnl_pct'])}"
        )
    return lines


def format_records_dashboard(app: App) -> str:
    stats = app.cycles.portfolio_stats()
    lines = [section("자산 대시보드", "📒"), ""]

    if is_dry(app):
        lines.extend([
            "<i>🧪 DRY 모드 — Toss API 미조회</i>",
            "",
            _realized_section(stats, cash_usd=0.0),
        ])
        active = _active_cycle_lines(app)
        if active:
            lines.extend(["", "<b>진행 회차 (평가)</b>", *active])
        return "\n".join(lines)

    acct = _fetch_account(app)
    fx_rate = acct["fx_rate"]
    unreal_krw = acct["unreal_usd"] * fx_rate if fx_rate > 0 else 0.0
    total_krw = acct["total_krw"]
    if total_krw <= 0 and fx_rate > 0:
        total_krw = acct["total_usd"] * fx_rate

    lines.extend([
        "<b>💰 총 자산</b>",
        f"   USD  <b>${acct['total_usd']:,.2f}</b>",
        f"   KRW  <b>₩{total_krw:,.0f}</b>" if total_krw > 0 else "   KRW  —",
        "",
        f"💵 예수금  <b>${acct['cash_usd']:,.2f}</b>",
        "",
        "<b>📈 미실현 손익</b>",
    ])

    if acct["unreal_pct"] is not None:
        lines.append(f"   {pnl_line(acct['unreal_usd'], acct['unreal_pct'])}")
    else:
        sign = "+" if acct["unreal_usd"] >= 0 else ""
        icon = "📈" if acct["unreal_usd"] >= 0 else "📉"
        lines.append(f"   {icon} {sign}${acct['unreal_usd']:,.2f}")

    if fx_rate > 0:
        sign = "+" if unreal_krw >= 0 else ""
        lines.append(f"   KRW  {sign}₩{unreal_krw:,.0f}")
        lines.extend(["", f"💱 환율  $1 = ₩{fx_rate:,.2f}"])
    else:
        lines.extend(["", "💱 환율  조회 실패"])

    lines.extend(["", DIVIDER, ""])
    lines.append(_realized_section(stats, acct["cash_usd"]))

    active = _active_cycle_lines(app)
    if active:
        lines.extend(["", "<b>진행 회차 (평가)</b>", *active])

    per_sym = stats.get("per_symbol", {})
    detail = [
        sym for sym in SYMBOLS
        if per_sym.get(sym, {}).get("realized_usd", 0) != 0 or per_sym.get(sym, {}).get("active")
    ]
    if detail:
        lines.extend(["", "<b>종목별 실현</b>"])
        for sym in detail:
            info = per_sym[sym]
            sign = "+" if info["realized_usd"] >= 0 else ""
            tag = " · 진행 중" if info.get("active") else ""
            lines.append(
                f"  {sym}  {sign}${info['realized_usd']:,.0f}"
                f"  ({info['completed_cycles']}회){tag}"
            )

    return "\n".join(lines)


def _realized_section(stats: dict, cash_usd: float) -> str:
    realized = stats["realized_usd"]
    completed = stats["completed_cycles"]
    active = stats["active_cycles"]
    pct = round(realized / cash_usd * 100, 2) if cash_usd > 0 else None
    sign = "+" if realized >= 0 else ""
    icon = "📈" if realized >= 0 else "📉"

    lines = [
        "<b>🏦 무한매수 실현 수익</b>",
        f"   완료 {completed}회  │  진행 {active}회",
        f"   실현  {icon} {sign}${realized:,.2f}",
    ]
    if pct is not None:
        lines.append(f"   예수금 대비  <b>{sign}{pct:.2f}%</b>")
    elif cash_usd <= 0:
        lines.append("   예수금 대비  — (예수금 조회 필요)")
    return "\n".join(lines)
