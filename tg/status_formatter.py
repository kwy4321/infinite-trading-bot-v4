"""Format /status — bot health + account cash only (/dashboard handles symbols)."""

from app import App


def _mode_label(app: App) -> str:
    if app.runtime.is_paused():
        return "⏸️ 정지"
    if app.settings.dry_run or not app.settings.has_toss:
        return "▶️ 가동 · DRY_RUN"
    return "▶️ 가동 · LIVE"


def format_status(app: App) -> str:
    market_open = app.broker.is_us_market_open_today()
    market = "🟢 개장" if market_open else "🔴 휴장"
    auto = "⏸️ 자동 실행 멈춤" if app.runtime.is_paused() else "⏰ 자동 실행 중"
    symbols = ", ".join(app.runtime.active_symbols())
    dry = app.settings.dry_run or not app.settings.has_toss

    lines = [
        f"🤖 <b>상태</b>",
        f"{_mode_label(app)} | 미증시 {market} | {auto}",
        f"종목: {symbols}",
        "",
        "💵 <b>계좌</b>",
    ]

    if not dry:
        buying = app.broker.get_buying_power("USD")
        raw = buying.get("cashBuyingPower") if buying else None
        if raw is not None:
            lines.append(f"달러 예수금: <b>${float(raw):,.2f}</b>")
        else:
            lines.append("달러 예수금: 조회 실패")

    manual = " | ".join(
        f"{sym} ${app.state.load(sym)['cash']:,.2f}"
        for sym in app.state.list_symbols()
    )
    lines.append(f"전략 예수금: {manual}")

    if dry:
        lines.append("<i>LIVE 전환 시 달러 예수금 API 조회</i>")
    else:
        lines.append("<i>종목별 T·보유 → /dashboard</i>")

    return "\n".join(lines)
