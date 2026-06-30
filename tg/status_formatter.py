"""Format /status — strategy progress (진행상황)."""

from app import App
from tg.format_helpers import is_dry, resolve_price
from tg.ui import DIVIDER, market_status_label, mode_label, pnl_line, section


def format_status(app: App) -> str:
    try:
        market = market_status_label(app.broker.get_us_market_status())
    except Exception:
        market = market_status_label("off_hours")

    paused = app.runtime.is_paused()
    dry = is_dry(app)
    run_mode = "🧪 DRY" if dry else "💹 LIVE"
    bot = "⏸️ 정지" if paused else "🤖 가동"
    auto = "⏸️ 멈춤" if paused else "⏰ 실행 중"

    lines = [
        section("진행상황", "📈"),
        f"🤖 봇      {bot}",
        f"⚙️ 모드    {run_mode}",
        f"⏰ 자동    {auto}",
        f"🇺🇸 시장   {market}",
        "",
    ]

    symbols = [app.runtime.default_symbol()]
    for sym in symbols:
        st = app.state.load(sym)
        price = resolve_price(app, sym)
        app.cycles.ensure_current(sym, st["principal"])
        live = app.cycles.calc_unrealized_pnl(sym, st["qty"], st["avg_price"], price)
        strat = mode_label(
            app.strategy.resolve_mode(
                st["qty"], st["T"], st["split_count"], st.get("force_one", False),
            ).value
        )

        lines.append(f"📦 <b>{sym}</b>")
        lines.append(f"🎯 T {st['T']:.2f}  │  {st['split_count']}분할  │  {strat}")

        if live:
            lines.append(f"🔢 회차 {live['cycle_no']}  │  {pnl_line(live['cycle_pnl_usd'], live['cycle_pnl_pct'])}")
        else:
            lines.append("🔢 회차 —  │  💤 시작 전")

        if st["qty"] > 0:
            pct = ""
            if st["avg_price"] > 0 and price > 0:
                p = (price - st["avg_price"]) / st["avg_price"] * 100
                pct = f"  ({p:+.1f}%)"
            price_txt = f"${price:.2f}" if price > 0 else "—"
            lines.append(f"📊 {st['qty']}주 @ ${st['avg_price']:.2f}  →  {price_txt}{pct}")
        else:
            lines.append("📊 보유  없음")

        lines.append(f"💰 원금  ${st['principal']:,.2f}")
        lines.append("")

    if dry:
        lines.append(f"<i>{DIVIDER}</i>")
        lines.append("<i>🧪 DRY 모드 · 전략 기록 기준</i>")

    if lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)
