"""Format /status — strategy progress (진행상황)."""

from app import App
from tg.format_helpers import is_dry, resolve_price
from tg.ui import (
    badge_auto,
    badge_bot,
    badge_live,
    code,
    dim,
    market_status_label,
    mode_label,
    pnl_line,
    quote,
    section,
    symbol_card,
    usd,
)


def format_status(app: App) -> str:
    try:
        market = market_status_label(app.broker.get_us_market_status())
    except Exception:
        market = market_status_label("off_hours")

    paused = app.runtime.is_paused()
    dry = is_dry(app)

    lines = [
        section("진행상황", "📈"),
        quote(
            f"{badge_bot(paused)}   ·   {badge_live(dry)}   ·   {market}",
            badge_auto(paused),
        ),
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

        t_str = f"{st['T']:.2f}"
        card = [
            symbol_card(sym),
            f"🎯 {dim('T')} {code(t_str)}　│　"
            f"{dim('분할')} {code(str(st['split_count']))}　│　{strat}",
        ]

        if live:
            card.append(
                f"🔢 {dim('회차')} {code(str(live['cycle_no']))}　│　"
                f"{pnl_line(live['cycle_pnl_usd'], live['cycle_pnl_pct'])}"
            )
        else:
            card.append(f"🔢 {dim('회차')} —　│　💤 {dim('시작 전')}")

        if st["qty"] > 0:
            pct_txt = ""
            if st["avg_price"] > 0 and price > 0:
                p = (price - st["avg_price"]) / st["avg_price"] * 100
                pct_txt = f"　{dim(f'({p:+.1f}%)')}"
            price_txt = usd(price) if price > 0 else "—"
            card.append(
                f"📊 {code(str(st['qty']) + '주')} @ {usd(st['avg_price'])}　"
                f"→　{price_txt}{pct_txt}"
            )
        else:
            card.append(f"📊 {dim('보유 없음')}")

        card.append(f"💰 {dim('원금')}　{usd(st['principal'])}")
        lines.append(quote(*card))

    if dry:
        lines.append(dim("🧪 DRY 모드 · 전략 기록 기준"))

    return "\n".join(lines)
