"""아침 브리핑 — 무매(라오어 무한매수) 진행 현황."""

from __future__ import annotations

from app import App
from core.trade_pnl import sell_realized_pnl
from render.html import dim, quote
from render.labels import side_icon
from render.numbers import realized_pnl_brief, section, t_transition
from services.trading_context import is_dry
from strategy.session_fill import us_session_date_from_when
from tg.status_formatter import build_symbol_status_lines


def _trades_for_session(app: App, symbol: str, session_date: str) -> list[dict]:
    """직전 미국 거래일(ET) 체결 — fill_log·회차 trades."""
    sym = symbol.upper()
    seen: set[tuple] = set()
    out: list[dict] = []

    def _add(entry: dict) -> None:
        when = entry.get("ordered_at") or entry.get("filled_at") or entry.get("at") or ""
        if us_session_date_from_when(when) != session_date:
            return
        key = (
            str(entry.get("side") or ""),
            int(entry.get("qty") or 0),
            round(float(entry.get("price") or 0), 4),
            str(when)[:19],
        )
        if key in seen:
            return
        seen.add(key)
        out.append(entry)

    st = app.state.load(sym)
    for entry in st.get("fill_log") or []:
        if str(entry.get("symbol") or sym).upper() != sym:
            continue
        _add(entry)

    cur = app.cycles.get_symbol_data(sym).get("current") or {}
    for tr in cur.get("trades") or []:
        _add(tr)

    return out


def _format_session_trades_line(session_label: str, trades: list[dict]) -> str:
    """직전 미국 거래일 매매 — 종목 카드 맨 아래 한 줄."""
    head = dim(f"직전 종가 LOC · {session_label} · ")
    if not trades:
        return head + dim("체결 없음")

    parts: list[str] = []
    for tr in trades:
        side = str(tr.get("side") or "").upper()
        side_txt = "매수" if side == "BUY" else "매도"
        icon = side_icon(side, style="arrow")
        qty = int(tr.get("qty") or 0)
        price = float(tr.get("price") or 0)
        part = f"{icon}{side_txt} {qty}주 @ ${price:,.2f}"
        if side == "SELL":
            pnl = sell_realized_pnl(tr)
            if pnl:
                part += f" · {realized_pnl_brief(pnl[0], pnl[1])}"
        parts.append(part)

    t_txt = t_transition(trades[0].get("t_before"), trades[-1].get("t_after"))
    body = " · ".join(parts)
    if t_txt and t_txt != "—":
        body = f"{body} · {t_txt}"
    return head + body


def format_strategy_briefing(app: App, session_date: str, *, session_label: str = "") -> str:
    """무매 현황 + 직전 종가 LOC 체결 요약."""
    symbols = app.runtime.active_symbols()
    label = session_label or session_date
    lines = [section("무매 현황", "♾️"), ""]

    if not symbols:
        lines.append(quote(dim("거래 종목 없음 · 설정 → 거래 종목")))
        return "\n".join(lines)

    for sym in symbols:
        card = build_symbol_status_lines(app, sym, brief=True)
        trades = _trades_for_session(app, sym, session_date)
        card.append(_format_session_trades_line(label, trades))
        lines.append(quote(*card))

    if is_dry(app):
        lines.append(dim("🧪 DRY 모드 · 전략 기록 기준"))

    return "\n".join(lines)
