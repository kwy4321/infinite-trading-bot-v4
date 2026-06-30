"""Format /history and /monthly — 기록 (종료·수익)."""

from app import App
from config.settings import SYMBOLS


def format_graduation_history(app: App, symbol: str) -> str:
    sym_data = app.cycles.get_symbol_data(symbol)
    completed = sym_data.get("completed", [])

    lines = [f"🎓 <b>종료 기록</b>  {symbol}", ""]

    if not completed:
        lines.append("종료된 회차 없음")
        return "\n".join(lines)

    for c in reversed(completed[-20:]):
        trades = c.get("buy_count", 0) + c.get("sell_count", 0)
        sign = "+" if c["profit_usd"] >= 0 else ""
        lines.append(
            f"<b>{c['ended_at']}</b>  ·  {c['cycle_no']}회차  ·  {trades}회 진행"
        )
        lines.append(f"  수익 {sign}${c['profit_usd']:,.2f}  ({sign}{c['profit_pct']:.2f}%)")
        lines.append("")

    if lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def format_profit_summary(app: App, year: int, symbol: str | None = None) -> str:
    label = symbol if symbol else "전체"
    summary = app.cycles.monthly_summary(symbol, year)

    lines = [f"📊 <b>수익현황</b>  {year}년  {label}", ""]

    if not summary:
        lines.append("해당 연도 종료 회차 없음")
        return "\n".join(lines)

    total_profit = 0.0
    total_buy = 0.0
    for month, info in summary.items():
        mm = int(month[5:7])
        pct = info["profit_pct_on_buy"]
        sign = "+" if pct >= 0 else ""
        lines.append(f"  {mm:02d}월  {sign}{pct:.2f}%")
        total_profit += info["profit_usd"]
        for d in info.get("details", []):
            total_buy += d.get("total_buy_usd", 0.0)

    if total_buy > 0:
        year_pct = round(total_profit / total_buy * 100, 2)
        sign = "+" if year_pct >= 0 else ""
        lines.extend(["", f"  <b>연간</b>  {sign}{year_pct:.2f}%"])

    return "\n".join(lines)
