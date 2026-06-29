"""Text dashboard for /dashboard."""

from app import App


def format_dashboard(app: App) -> str:
    lines = ["📊 <b>라오어 무한매수 4.0 대시보드</b>\n"]
    paused = app.runtime.is_paused()
    lines.append(f"상태: {'⏸️ 일시정지' if paused else '▶️ 가동 중'}")
    lines.append(f"활성 종목: {', '.join(app.runtime.active_symbols())}\n")

    for sym in app.state.list_symbols():
        st = app.state.load(sym)
        api = app.broker.get_holdings_item(sym)
        price = api["current_price"] or app.broker.get_price(sym)
        summary = app.strategy.summarize(
            sym, price, st["avg_price"], st["qty"], st["T"],
            st["cash"], st["split_count"],
        )
        app.cycles.ensure_current(sym, st["principal"])
        live = app.cycles.calc_unrealized_pnl(sym, st["qty"], st["avg_price"], price)
        cycle_txt = ""
        if live:
            sign = "+" if live["cycle_pnl_usd"] >= 0 else ""
            cycle_txt = f" | 회차{live['cycle_no']} {sign}${live['cycle_pnl_usd']:,.0f}"
        profit = 0.0
        if st["avg_price"] > 0 and price > 0:
            profit = (price - st["avg_price"]) / st["avg_price"] * 100
        lines.append(
            f"<b>{sym}</b> T={st['T']:.2f} | {st['qty']}주 @ ${st['avg_price']:.2f} "
            f"({profit:+.1f}%){cycle_txt}\n"
            f"  모드 {summary['mode']} | 1회 ${summary['one_buy_amount']:,.0f} | "
            f"예수금 ${st['cash']:,.0f} (수동)"
        )
    return "\n".join(lines)
