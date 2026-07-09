"""Format /balance — account snapshot (계좌현황)."""

from broker.toss_client import _money
from app import App
from config.settings import SYMBOLS
from tg.ui import THIN, code, empty, krw, quote, row, section, subsection, symbol_card, usd


def _cash_usd(buying: dict) -> float:
    if not buying:
        return 0.0
    raw = buying.get("cashBuyingPower", buying.get("cash", buying))
    return _money(raw, "usd") if isinstance(raw, dict) else float(raw or 0)


def _cash_krw(buying: dict) -> float:
    if not buying:
        return 0.0
    raw = buying.get("cashBuyingPower", buying.get("cash", buying))
    return _money(raw, "krw")


def format_balance(app: App) -> str:
    broker = app.broker
    lines = [section("계좌현황", "💼"), ""]

    buying_usd = broker.get_buying_power("USD")
    buying_krw = broker.get_buying_power("KRW")
    cash_usd = _cash_usd(buying_usd)
    cash_krw = _cash_krw(buying_krw)

    overview = broker.get_holdings_overview() or {}
    items = overview.get("items", [])
    tracked = [i for i in items if i.get("symbol", "").upper() in SYMBOLS]
    display = tracked or items

    stock_usd = sum(_money(i.get("marketValue"), "usd") for i in display)
    stock_krw = sum(_money(i.get("marketValue"), "krw") for i in display)

    total_usd = _money(overview.get("totalEvaluationAmount"), "usd")
    total_krw = _money(overview.get("totalEvaluationAmount"), "krw")
    if total_usd <= 0:
        total_usd = cash_usd + stock_usd
    if total_krw <= 0:
        total_krw = cash_krw + stock_krw

    fx = broker.get_exchange_rate("USD", "KRW")
    fx_rate = float(fx.get("rate") or fx.get("midRate") or 0)
    if total_krw <= 0 and fx_rate > 0 and total_usd > 0:
        total_krw = total_usd * fx_rate

    summary = [
        row("🇺🇸", "총 자산", usd(total_usd)),
    ]
    if total_krw > 0:
        summary.append(row("🇰🇷", "총 자산", krw(total_krw)))
    if cash_krw > 0:
        summary.append(
            row("💵", "예수금", f"{usd(cash_usd)}  ·  {krw(cash_krw)}"),
        )
    else:
        summary.append(row("💵", "예수금", usd(cash_usd)))
    if fx_rate > 0:
        summary.append(row("💱", "환율", code(f"$1 = ₩{fx_rate:,.2f}")))

    lines.extend([subsection("요약"), quote(*summary), ""])

    if display:
        rows = []
        for i, item in enumerate(display):
            if i > 0:
                rows.append(THIN)
            rows.extend(_holding_rows(item))
        lines.append(subsection("보유 종목"))
        lines.append(quote(*rows))
    else:
        lines.append(empty("보유 종목 없음"))

    return "\n".join(lines)


def _holding_rows(item: dict) -> list[str]:
    sym = item.get("symbol", "?").upper()
    qty = float(item.get("quantity", 0) or 0)
    avg = float(item.get("averagePurchasePrice", 0) or 0)
    if avg == 0:
        cost = item.get("cost", {})
        avg = float(cost.get("averagePrice", 0) or 0)
    last = float(item.get("lastPrice", 0) or 0)
    mkt_usd = _money(item.get("marketValue"), "usd")
    mkt_krw = _money(item.get("marketValue"), "krw")
    if mkt_usd == 0 and qty and last:
        mkt_usd = qty * last

    return [
        symbol_card(sym),
        f"{dim('수량')} {code(f'{qty:g}주')}",
        f"{dim('평단')} {usd(avg)}",
        f"{dim('평가')} {usd(mkt_usd)}" + (f"  ·  {krw(mkt_krw)}" if mkt_krw > 0 else ""),
    ]
