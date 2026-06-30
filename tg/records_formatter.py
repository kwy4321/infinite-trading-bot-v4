"""Format /history and /monthly — 기록 (종료·수익)."""

from app import App
from tg.ui import (
    THIN,
    bold,
    code,
    dim,
    empty,
    month_bar,
    pnl_line,
    quote,
    quote_exp,
    row,
    section,
    symbol_card,
)


def format_graduation_history(app: App, symbol: str) -> str:
    sym_data = app.cycles.get_symbol_data(symbol)
    completed = sym_data.get("completed", [])

    lines = [
        section("종료 기록", "🎓"),
        row("📦", "종목", symbol_card(symbol)),
        "",
    ]

    if not completed:
        lines.append(empty("기록 없음"))
        return "\n".join(lines)

    entries = []
    for c in reversed(completed[-20:]):
        trades = c.get("buy_count", 0) + c.get("sell_count", 0)
        entries.append(f"📅 {bold(c['ended_at'])}")
        entries.append(
            f"🔢 {code(str(c['cycle_no']) + '회차')}　│　"
            f"{dim('매매')} {code(str(trades) + '회')}"
        )
        entries.append(pnl_line(c["profit_usd"], c["profit_pct"]))
        entries.append(THIN)
    if entries and entries[-1] == THIN:
        entries.pop()

    lines.append(quote_exp(*entries))
    return "\n".join(lines)


def format_profit_summary(app: App, year: int, symbol: str | None = None) -> str:
    label = symbol if symbol else "전체"
    summary = app.cycles.monthly_summary(symbol, year)

    lines = [
        section("수익현황", "📅"),
        row("🗓", f"{year}년", f"📦 {code(label)}"),
        "",
    ]

    if not summary:
        lines.append(empty("해당 연도 기록 없음"))
        return "\n".join(lines)

    total_profit = 0.0
    total_buy = 0.0
    rows = []
    for month, info in summary.items():
        mm = int(month[5:7])
        pct = info["profit_pct_on_buy"]
        sign = "+" if pct >= 0 else ""
        rows.append(f"{month_bar(pct >= 0)} {code(f'{mm:02d}월')}　{dim(f'{sign}{pct:.2f}%')}")
        total_profit += info["profit_usd"]
        for d in info.get("details", []):
            total_buy += d.get("total_buy_usd", 0.0)

    lines.append(quote(*rows))

    if total_buy > 0:
        year_pct = round(total_profit / total_buy * 100, 2)
        lines.append(f"🏆 {dim('연간')}　{pnl_line(total_profit, year_pct)}")

    return "\n".join(lines)
