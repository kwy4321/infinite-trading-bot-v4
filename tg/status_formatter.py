"""Format /status — strategy progress (진행상황)."""

from app import App


def format_status(app: App) -> str:
    market_open = app.broker.is_us_market_open_today()
    market = "개장" if market_open else "휴장"
    paused = app.runtime.is_paused()
    dry = app.settings.dry_run or not app.settings.has_toss
    mode = "DRY_RUN" if dry else "LIVE"
    bot = "⏸️ 정지" if paused else "▶️ 가동"
    auto = "⏸️ 멈춤" if paused else "⏰ 실행 중"

    lines = [
        "📈 <b>진행상황</b>",
        "",
        f"봇 {bot} · {mode} · 자동 {auto}",
        f"미증시 {market}",
        "",
    ]

    for sym in app.state.list_symbols():
        st = app.state.load(sym)
        api = app.broker.get_holdings_item(sym)
        price = api["current_price"] or app.broker.get_price(sym)
        app.cycles.ensure_current(sym, st["principal"])
        live = app.cycles.calc_unrealized_pnl(sym, st["qty"], st["avg_price"], price)

        mode = app.strategy.detect_mode(st["qty"], st["T"], st["split_count"]).value

        lines.append(f"<b>{sym}</b>")
        lines.append(f"  T {st['T']:.2f} · {st['split_count']}분할 · {mode}")

        if live:
            sign = "+" if live["cycle_pnl_usd"] >= 0 else ""
            lines.append(
                f"  회차 {live['cycle_no']} · {sign}${live['cycle_pnl_usd']:,.0f} ({sign}{live['cycle_pnl_pct']:.1f}%)"
            )
        else:
            lines.append("  회차 —")

        if st["qty"] > 0:
            pct = ""
            if st["avg_price"] > 0 and price > 0:
                p = (price - st["avg_price"]) / st["avg_price"] * 100
                pct = f" ({p:+.1f}%)"
            price_txt = f"${price:.2f}" if price > 0 else "—"
            lines.append(f"  {st['qty']}주 @ ${st['avg_price']:.2f} · 현재 {price_txt}{pct}")
        else:
            lines.append("  무포지션")

        lines.append(f"  전략 예수금 ${st['cash']:,.2f}")
        lines.append("")

    if lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)
