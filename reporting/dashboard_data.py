"""Read-only snapshots from bot state — Streamlit / Google Sheets 공통."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from config.settings import SYMBOLS
from tg.format_helpers import is_dry, resolve_price
from tg.ui import mode_label

if TYPE_CHECKING:
    from app import App


def _trade_row(symbol: str, tr: dict, *, cycle_no: int | None = None, cycle_status: str = "") -> dict:
    when = tr.get("ordered_at") or tr.get("filled_at") or tr.get("at") or ""
    return {
        "symbol": symbol,
        "cycle_no": cycle_no or "",
        "cycle_status": cycle_status,
        "date": str(when)[:10] if when else "",
        "datetime": str(when),
        "side": tr.get("side", ""),
        "qty": int(tr.get("qty", 0)),
        "price": float(tr.get("price", 0)),
        "amount_usd": round(float(tr.get("price", 0)) * int(tr.get("qty", 0)), 2),
        "action": tr.get("action") or "",
        "t_before": tr.get("t_before", ""),
        "t_after": tr.get("t_after", ""),
        "avg_after": tr.get("avg_after", ""),
        "qty_after": tr.get("qty_after", ""),
        "source": tr.get("source", ""),
        "order_id": tr.get("order_id", ""),
        "note": tr.get("note", ""),
    }


def collect_symbol_status(app: "App", symbol: str) -> dict:
    st = app.state.load(symbol)
    price = resolve_price(app, symbol)
    mode = app.strategy.resolve_mode_from_state(st).value
    progress = app.cycles.cycle_progress(symbol, trading=True, qty=st["qty"])
    live = app.cycles.calc_unrealized_pnl(symbol, st["qty"], st["avg_price"], price)
    sym = app.cycles.get_symbol_data(symbol)
    cur = sym.get("current") or {}
    return {
        "symbol": symbol,
        "active": symbol in app.runtime.active_symbols(),
        "mode": mode,
        "mode_label": mode_label(mode, brief=True),
        "T": float(st.get("T", 0)),
        "split_count": int(st.get("split_count", 40)),
        "principal": float(st.get("principal", 0)),
        "qty": int(st.get("qty", 0)),
        "avg_price": float(st.get("avg_price", 0)),
        "current_price": float(price or 0),
        "eval_usd": round(int(st.get("qty", 0)) * float(price or 0), 2),
        "cycle_no": cur.get("cycle_no", progress or 0),
        "cycle_started_at": cur.get("started_at", ""),
        "cycle_pnl_usd": live.get("cycle_pnl_usd", 0) if live else 0,
        "cycle_pnl_pct": live.get("cycle_pnl_pct", 0) if live else 0,
        "force_one": bool(st.get("force_one", False)),
        "reverse_mode": bool(st.get("reverse_mode", False)),
        "take_profit_pct": app.strategy.resolve_take_profit(symbol, st.get("take_profit_pct")),
    }


def collect_portfolio_snapshot(app: "App") -> dict:
    stats = app.cycles.portfolio_stats()
    account = {
        "cash_usd": 0.0,
        "total_usd": 0.0,
        "total_krw": 0.0,
        "unreal_usd": 0.0,
        "unreal_pct": None,
        "fx_rate": 0.0,
    }
    if not is_dry(app) and app.settings.has_toss:
        try:
            from tg.records_dashboard_formatter import _fetch_account
            account = _fetch_account(app)
        except Exception:
            pass
    return {
        "updated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "dry_run": is_dry(app),
        "paused": app.runtime.is_paused(),
        "account": account,
        "realized_usd": stats.get("realized_usd", 0),
        "completed_cycles": stats.get("completed_cycles", 0),
        "active_cycles": stats.get("active_cycles", 0),
        "symbols": [collect_symbol_status(app, sym) for sym in SYMBOLS],
    }


def collect_all_trades(app: "App") -> list[dict]:
    rows: list[dict] = []
    for symbol in SYMBOLS:
        sym = app.cycles.get_symbol_data(symbol)
        cur = sym.get("current")
        if cur:
            for tr in cur.get("trades") or []:
                rows.append(_trade_row(
                    symbol, tr,
                    cycle_no=cur.get("cycle_no"),
                    cycle_status="진행중",
                ))
        for c in sym.get("completed") or []:
            for tr in c.get("trades") or []:
                rows.append(_trade_row(
                    symbol, tr,
                    cycle_no=c.get("cycle_no"),
                    cycle_status="완료",
                ))
    rows.sort(key=lambda r: r.get("datetime") or "")
    return rows


def collect_completed_cycles(app: "App") -> list[dict]:
    rows: list[dict] = []
    for symbol in SYMBOLS:
        for c in app.cycles.get_symbol_data(symbol).get("completed") or []:
            rows.append({
                "symbol": symbol,
                "cycle_no": c.get("cycle_no"),
                "started_at": c.get("started_at", ""),
                "ended_at": c.get("ended_at", ""),
                "principal": c.get("principal", 0),
                "total_buy_usd": c.get("total_buy_usd", 0),
                "total_sell_usd": c.get("total_sell_usd", 0),
                "profit_usd": c.get("profit_usd", 0),
                "profit_pct": c.get("profit_pct", 0),
                "max_T": c.get("max_T", 0),
                "buy_count": c.get("buy_count", 0),
                "sell_count": c.get("sell_count", 0),
            })
    rows.sort(key=lambda r: (r.get("symbol", ""), r.get("ended_at", "")))
    return rows


def collect_monthly_rows(app: "App", year: int | None = None) -> list[dict]:
    year = year or datetime.date.today().year
    rows: list[dict] = []
    for symbol in (None, *SYMBOLS):
        label = symbol or "전체"
        summary = app.cycles.monthly_summary(symbol, year)
        for month, info in sorted(summary.items()):
            rows.append({
                "year": year,
                "month": month,
                "scope": label,
                "cycles": info.get("cycles", 0),
                "profit_usd": info.get("profit_usd", 0),
                "profit_pct_on_buy": info.get("profit_pct_on_buy", 0),
            })
    return rows
