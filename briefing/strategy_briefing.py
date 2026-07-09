"""아침 브리핑 — 무매(라오어 무한매수) 진행 현황."""

from __future__ import annotations

from app import App
from cycles.cycle_tracker import CycleTracker
from strategy.session_fill import us_session_date_from_when
from tg.format_helpers import is_dry
from tg.status_formatter import build_symbol_status_lines
from tg.ui import dim, quote, section


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


def format_strategy_briefing(app: App, session_date: str, *, session_label: str = "") -> str:
    """무매 현황 + 직전 종가 LOC 체결 요약."""
    symbols = app.runtime.active_symbols()
    label = session_label or session_date
    lines = [section("무매 현황", "📊"), ""]

    if not symbols:
        lines.append(quote(dim("거래 종목 없음 · ⚙️ 설정 → 📡 거래 종목")))
        return "\n".join(lines)

    for sym in symbols:
        card = build_symbol_status_lines(app, sym)
        trades = _trades_for_session(app, sym, session_date)
        card.append("")
        card.append(f"🌙 {dim(f'직전 종가 LOC · {label}')}")
        if trades:
            for tr in trades:
                card.append(f"  {CycleTracker.format_trade_line(sym, tr).strip()}")
        else:
            card.append(f"  {dim('체결 없음')}")
        lines.append(quote(*card))

    if is_dry(app):
        lines.append(dim("🧪 DRY 모드 · 전략 기록 기준"))

    return "\n".join(lines)
