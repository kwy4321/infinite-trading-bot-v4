"""Format /dashboard — records asset dashboard (자산·손익·환율·실현수익)."""

from __future__ import annotations

from app import App
from services.account_service import fetch_account_snapshot
from services.market_data import resolve_price
from services.trading_context import is_dry
from tg.ui import (
    DIVIDER,
    code,
    dim,
    krw,
    pnl_line,
    pnl_line_precise,
    quote,
    row,
    section,
    subsection,
    symbol_card,
    trend_arrow,
    usd,
)



def _fetch_account(app: App) -> dict:
    """하위 호환 — 실제 조회는 services.account_service 가 담당한다."""
    return fetch_account_snapshot(app).as_dict()


def _qty_by_symbol(app: App) -> dict[str, int]:
    """거래 중인 종목의 보유 수량 (미거래 종목은 집계·표시에서 제외)."""
    return {
        sym: int(app.state.load(sym).get("qty", 0))
        for sym in app.runtime.active_symbols()
    }


def _active_cycle_lines(app: App, stats: dict) -> list[str]:
    lines = []
    for sym in app.runtime.active_symbols():
        progress = stats["per_symbol"].get(sym, {}).get("cycle_progress", 0)
        if progress <= 0:
            continue
        st = app.state.load(sym)
        price = resolve_price(app, sym)
        live = app.cycles.calc_unrealized_pnl(sym, st["qty"], st["avg_price"], price)
        if not live:
            continue
        lines.append(
            f"{symbol_card(sym)}　#{code(str(progress))}　"
            f"{pnl_line(live['cycle_pnl_usd'], live['cycle_pnl_pct'])}"
        )
    return lines


def _tracked_symbols(app: App) -> list[str]:
    return app.runtime.active_symbols()


def _cycle_progress_rows(app: App, stats: dict) -> list[str]:
    rows = []
    for sym in app.runtime.active_symbols():
        progress = stats["per_symbol"].get(sym, {}).get("cycle_progress", 0)
        rows.append(row("🔢", sym, code(f"{progress}회차")))
    return rows


def _realized_block(app: App, stats: dict, cash_usd: float) -> list[str]:
    realized = stats["realized_usd"]
    completed = stats["completed_cycles"]
    pct_val = round(realized / cash_usd * 100, 2) if cash_usd > 0 else None

    rows = [
        row("📊", "완료", code(f"{completed}회")),
        *_cycle_progress_rows(app, stats),
    ]
    if pct_val is not None:
        rows.append(pnl_line_precise(realized, pct_val))
        sign = "+" if pct_val >= 0 else ""
        rows.append(f"{dim('예수금 대비')}　{code(f'{sign}{pct_val:.2f}%')}")
    else:
        sign = "+" if realized >= 0 else ""
        rows.append(f"{trend_arrow(realized >= 0)} {code(f'{sign}${realized:,.2f}')}")
        if cash_usd <= 0:
            rows.append(f"{dim('예수금 대비')}　—")
    return [subsection("🏦 실현 수익"), quote(*rows)]


def format_records_dashboard(app: App) -> str:
    tracked = _tracked_symbols(app)
    stats = app.cycles.portfolio_stats(tracked, _qty_by_symbol(app))
    lines = [section("자산 대시보드", "📒"), ""]

    if is_dry(app):
        lines.append(dim("🧪 DRY 모드 — Toss API 미조회"))
        lines.append("")
        lines.extend(_realized_block(app, stats, 0.0))
        active = _active_cycle_lines(app, stats)
        if active:
            lines.extend(["", subsection("⏳ 진행 회차 (평가)"), quote(*active)])
        return "\n".join(lines)

    acct = _fetch_account(app)
    fx_rate = acct["fx_rate"]
    unreal_krw = acct["unreal_usd"] * fx_rate if fx_rate > 0 else 0.0
    total_krw = acct["total_krw"]
    if total_krw <= 0 and fx_rate > 0:
        total_krw = acct["total_usd"] * fx_rate

    asset_rows = [row("🇺🇸", "USD", usd(acct["total_usd"]))]
    if total_krw > 0:
        asset_rows.append(row("🇰🇷", "KRW", krw(total_krw)))
    asset_rows.append(row("💵", "예수금", usd(acct["cash_usd"])))
    lines.extend([subsection("💰 총 자산"), quote(*asset_rows), ""])

    unreal_rows = []
    if acct["unreal_pct"] is not None:
        unreal_rows.append(pnl_line_precise(acct["unreal_usd"], acct["unreal_pct"]))
    else:
        u = acct["unreal_usd"]
        sign = "+" if u >= 0 else ""
        unreal_rows.append(f"{trend_arrow(u >= 0)} {code(f'{sign}${u:,.2f}')}")
    if fx_rate > 0:
        sign = "+" if unreal_krw >= 0 else ""
        unreal_rows.append(row("🇰🇷", "KRW", code(f"{sign}₩{unreal_krw:,.0f}")))
    lines.extend([subsection("📈 미실현 손익"), quote(*unreal_rows)])

    if fx_rate > 0:
        lines.append(row("💱", "환율", code(f"$1 = ₩{fx_rate:,.2f}")))
    else:
        lines.append(row("💱", "환율", dim("조회 실패")))

    lines.extend(["", DIVIDER, ""])
    lines.extend(_realized_block(app, stats, acct["cash_usd"]))

    active = _active_cycle_lines(app, stats)
    if active:
        lines.extend(["", subsection("⏳ 진행 회차 (평가)"), quote(*active)])

    per_sym = stats.get("per_symbol", {})
    detail = [
        sym for sym in tracked
        if per_sym.get(sym, {}).get("realized_usd", 0) != 0 or per_sym.get(sym, {}).get("active")
    ]
    if detail:
        sym_rows = []
        for sym in detail:
            info = per_sym[sym]
            r = info["realized_usd"]
            sign = "+" if r >= 0 else ""
            tag = dim(" · 진행 중") if info.get("active") else ""
            cycles_txt = "(" + str(info["completed_cycles"]) + "회)"
            sym_rows.append(
                f"{symbol_card(sym)}　{code(f'{sign}${r:,.0f}')}"
                f"　{dim(cycles_txt)}{tag}"
            )
        lines.extend(["", subsection("📦 종목별 실현"), quote(*sym_rows)])

    return "\n".join(lines)
