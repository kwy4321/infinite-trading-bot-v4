"""Format /status — strategy progress (전략 진행, 메인과 역할 분리)."""

from app import App
from tg.format_helpers import is_dry, resolve_price
from tg.ui import (
    code,
    dim,
    mode_label,
    pnl_line,
    quote,
    section,
    symbol_card,
    usd,
)


def build_symbol_status_lines(app: App, sym: str) -> list[str]:
    """종목 1개 전략 카드 본문 (quote 래퍼 없음)."""
    st = app.state.load(sym)
    price = resolve_price(app, sym)
    progress = app.cycles.cycle_progress(sym, trading=True, qty=st["qty"])
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

    if progress > 0 and live:
        card.append(
            f"🔢 {dim('회차')} {code(f'{progress}회차')}　│　"
            f"{pnl_line(live['cycle_pnl_usd'], live['cycle_pnl_pct'])}"
        )
    elif progress > 0:
        card.append(f"🔢 {dim('회차')} {code(f'{progress}회차')}")
    else:
        card.append(f"🔢 {dim('회차')} {code('0회차')}　│　💤 {dim('시작 전')}")

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
    return card


def format_status(app: App, *, title: str = "전략 현황", icon: str = "📈") -> str:
    symbols = app.runtime.active_symbols()
    lines = [section(title, icon), ""]

    if not symbols:
        lines.append(quote(dim("거래 종목 없음 · ⚙️ 설정 → 📡 거래 종목")))
        return "\n".join(lines)

    for sym in symbols:
        lines.append(quote(*build_symbol_status_lines(app, sym)))

    if is_dry(app):
        lines.append(dim("🧪 DRY 모드 · 전략 기록 기준"))

    return "\n".join(lines)
