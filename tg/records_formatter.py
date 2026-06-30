"""Format /history and /monthly — 기록 (종료·수익)."""

from app import App
from tg.ui import DIVIDER, pnl_line, section


def format_graduation_history(app: App, symbol: str) -> str:
    sym_data = app.cycles.get_symbol_data(symbol)
    completed = sym_data.get("completed", [])

    lines = [section("종료 기록", "🎓"), f"📦 종목  {symbol}", ""]

    if not completed:
        lines.append("📭 기록 없음")
        return "\n".join(lines)

    for c in reversed(completed[-20:]):
        trades = c.get("buy_count", 0) + c.get("sell_count", 0)
        lines.append(f"📅 <b>{c['ended_at']}</b>")
        lines.append(f"🔢 {c['cycle_no']}회차  │  🔁 {trades}회")
        lines.append(pnl_line(c["profit_usd"], c["profit_pct"]))
        lines.append("")

    if lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def format_profit_summary(app: App, year: int, symbol: str | None = None) -> str:
    label = symbol if symbol else "전체"
    summary = app.cycles.monthly_summary(symbol, year)

    lines = [section("수익현황", "📅"), f"🗓 {year}년  │  📦 {label}", ""]

    if not summary:
        lines.append("📭 해당 연도 기록 없음")
        return "\n".join(lines)

    total_profit = 0.0
    total_buy = 0.0
    for month, info in summary.items():
        mm = int(month[5:7])
        pct = info["profit_pct_on_buy"]
        sign = "+" if pct >= 0 else ""
        bar = "🟩" if pct >= 0 else "🟥"
        lines.append(f"{bar} {mm:02d}월  {sign}{pct:.2f}%")
        total_profit += info["profit_usd"]
        for d in info.get("details", []):
            total_buy += d.get("total_buy_usd", 0.0)

    if total_buy > 0:
        year_pct = round(total_profit / total_buy * 100, 2)
        lines.extend(["", DIVIDER, f"🏆 연간  {pnl_line(total_profit, year_pct)}"])

    return "\n".join(lines)
