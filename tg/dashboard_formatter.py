"""Text dashboard for /dashboard — compact portfolio overview."""

from app import App


def format_dashboard(app: App) -> str:
    lines = ["📊 <b>라오어 무한매수 4.0 대시보드</b>\n"]
    paused = app.runtime.is_paused()
    lines.append(f"상태: {'⏸️ 자동 실행 멈춤' if paused else '⏰ 자동 실행 중'}")
    lines.append(f"활성 종목: {', '.join(app.runtime.active_symbols())}\n")

    for sym in app.state.list_symbols():
        st = app.state.load(sym)
        api = app.broker.get_holdings_item(sym)
        price = api["current_price"] or app.broker.get_price(sym)
        app.cycles.ensure_current(sym, st["principal"])
        live = app.cycles.calc_unrealized_pnl(sym, st["qty"], st["avg_price"], price)

        profit = 0.0
        if st["avg_price"] > 0 and price > 0:
            profit = (price - st["avg_price"]) / st["avg_price"] * 100

        if st["qty"] > 0:
            pos_txt = f"{st['qty']}주 @ ${st['avg_price']:.2f} ({profit:+.1f}%)"
        else:
            pos_txt = "무포지션"

        price_txt = f"${price:.2f}" if price > 0 else "—"
        cycle_txt = "회차 없음"
        if live:
            sign = "+" if live["cycle_pnl_usd"] >= 0 else ""
            cycle_txt = f"회차{live['cycle_no']} {sign}${live['cycle_pnl_usd']:,.0f} ({sign}{live['cycle_pnl_pct']:.1f}%)"

        lines.append(
            f"<b>{sym}</b> {price_txt} | {pos_txt}\n"
            f"  {cycle_txt}"
        )
    return "\n".join(lines)
