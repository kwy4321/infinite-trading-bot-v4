"""Read-only snapshots from bot state — Streamlit / Google Sheets 공통."""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from config.settings import DATA_DIR, SYMBOLS
from tg.format_helpers import is_dry, resolve_price
from tg.ui import mode_label

if TYPE_CHECKING:
    from app import App

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


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


def collect_symbol_status(app: "App", symbol: str, *, fetch_live_price: bool = False) -> dict:
    st = app.state.load(symbol)
    if fetch_live_price and not is_dry(app):
        price = resolve_price(app, symbol)
    else:
        price = float(st.get("avg_price") or 0)
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


def collect_sheet_symbol_status(app: "App") -> list[dict]:
    """Sheets 종목현황 — 거래 중인 종목만."""
    premium = app.runtime.premium_default()
    rows: list[dict] = []
    for symbol in app.runtime.active_symbols():
        st = app.state.load(symbol)
        row = collect_symbol_status(app, symbol, fetch_live_price=False)
        row["mode_label"] = mode_label(str(row.get("mode", "")), brief=True)
        qty = int(st.get("qty") or 0)
        avg = float(st.get("avg_price") or 0)
        row["purchase_usd"] = round(avg * qty, 2) if qty and avg else 0
        plan_price = float(row.get("current_price") or avg or 0)
        plan = app.strategy.get_plan_from_state(
            symbol, plan_price, st, premium,
            available_cash=max(0.0, float(st.get("principal", 0))),
        )
        row["star_price"] = float(plan.get("star_price") or 0)
        row["star_pct"] = float(plan.get("star_pct") or 0)
        row["take_profit_pct"] = plan.get("take_profit_pct") or row["take_profit_pct"]
        rows.append(row)
    return rows


def collect_portfolio_snapshot(app: "App", *, fetch_live_price: bool = False) -> dict:
    stats = app.cycles.portfolio_stats()
    account = {
        "cash_usd": 0.0,
        "total_usd": 0.0,
        "total_krw": 0.0,
        "unreal_usd": 0.0,
        "unreal_pct": None,
        "fx_rate": 0.0,
    }
    if fetch_live_price and not is_dry(app) and app.settings.has_toss:
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
        "symbols": [
            collect_symbol_status(app, sym, fetch_live_price=fetch_live_price)
            for sym in app.runtime.active_symbols()
        ],
    }


def prepare_ledger_for_export(
    app: "App", *, rebuild_broker: bool = True, broker_timeout_sec: float = 25.0,
) -> dict:
    """fill_log·토스 체결 → cycles.current.trades 반영 (Sheets/대시보드 수집 전)."""
    import concurrent.futures

    result: dict = {
        "synced_symbols": [],
        "fill_log_entries": 0,
        "broker_symbols": [],
        "errors": [],
    }
    is_live = rebuild_broker and not is_dry(app) and app.settings.has_toss

    def _rebuild_one(symbol: str, fill_log: list, qty: int) -> int:
        from strategy.fill_reconciler import FillReconciler

        st = app.state.load(symbol)
        order_ids = FillReconciler.collect_known_order_ids(app, symbol, st=st)
        broker_fills = app.broker.list_broker_fills(
            symbol, days=365, max_orders=500, extra_order_ids=order_ids,
        )
        if not broker_fills:
            return 0
        return app.cycles.rebuild_trades_from_broker(symbol, broker_fills, fill_log, qty)

    for symbol in SYMBOLS:
        st = app.state.load(symbol)
        fill_log = list(st.get("fill_log") or [])
        principal = float(st.get("principal") or 0) or 10000.0
        qty = int(st.get("qty") or 0)
        sym = app.cycles.get_symbol_data(symbol)
        has_trades = bool((sym.get("current") or {}).get("trades"))

        if fill_log:
            result["fill_log_entries"] += len(fill_log)

        if fill_log or qty > 0 or has_trades:
            app.cycles.ensure_current(symbol, principal)

        if is_live and qty > 0:
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    fut = pool.submit(_rebuild_one, symbol, fill_log, qty)
                    n = fut.result(timeout=broker_timeout_sec)
                if n:
                    result["broker_symbols"].append(symbol)
            except concurrent.futures.TimeoutError:
                logger.warning("broker rebuild timeout %s", symbol)
                result["errors"].append(f"{symbol}: broker timeout")
            except Exception as exc:
                logger.exception("broker rebuild failed %s", symbol)
                result["errors"].append(f"{symbol}: {exc}")

        if fill_log:
            app.cycles.sync_trades_from_fill_log(symbol, fill_log, principal)

        app.cycles.backfill_trade_t_metadata(symbol)
        app.cycles.dedupe_symbol_trades(symbol)

        if fill_log or qty > 0 or has_trades:
            result["synced_symbols"].append(symbol)

    return result


def ledger_data_sources(app: "App") -> dict:
    """로컬 데이터 파일 존재·건수 — 0건일 때 원인 확인용."""
    sources: dict = {
        "data_dir": str(DATA_DIR),
        "cycles_json": (DATA_DIR / "cycles.json").is_file(),
        "symbols": {},
    }
    for symbol in SYMBOLS:
        state_path = DATA_DIR / f"{symbol}.json"
        st = app.state.load(symbol)
        sym = app.cycles.get_symbol_data(symbol)
        cur = sym.get("current") or {}
        sources["symbols"][symbol] = {
            "state_file": state_path.is_file(),
            "fill_log": len(st.get("fill_log") or []),
            "current_trades": len(cur.get("trades") or []),
            "completed_cycles": len(sym.get("completed") or []),
        }
    return sources


def collect_all_trades(app: "App") -> list[dict]:
    rows: list[dict] = []
    for symbol in SYMBOLS:
        sym = app.cycles.get_symbol_data(symbol)
        st = app.state.load(symbol)
        fill_log = st.get("fill_log") or []
        cur = sym.get("current")
        trades = app.cycles._collect_trades(sym, symbol, fill_log)
        if trades:
            cycle_no = (cur or {}).get("cycle_no", "")
            cycle_status = "진행중" if cur else ""
            for tr in trades:
                rows.append(_trade_row(
                    symbol, tr,
                    cycle_no=cycle_no,
                    cycle_status=cycle_status,
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


def _format_t_change(t_before, t_after) -> str:
    try:
        if t_before not in (None, "") and t_after not in (None, ""):
            tb, ta = float(t_before), float(t_after)
            if tb != ta:
                return f"{tb:g} → {ta:g}"
            return f"{ta:g}"
        if t_after not in (None, ""):
            return f"{float(t_after):g}"
        if t_before not in (None, ""):
            return f"{float(t_before):g}"
    except (TypeError, ValueError):
        pass
    return "—"


def _to_kst_date(when: str) -> str:
    raw = str(when or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(KST).strftime("%Y-%m-%d")
    except ValueError:
        return raw[:10]


def _enrich_sheet_trade_rows(rows: list[dict]) -> None:
    """종목별 평단 추적 → 매도 건별 실현손익 + 연번."""
    by_sym: dict[str, list[dict]] = {}
    for r in rows:
        by_sym.setdefault(r["symbol"], []).append(r)

    for sym_rows in by_sym.values():
        sym_rows.sort(key=lambda r: r.get("datetime") or "")
        running_qty = 0
        running_avg = 0.0
        for r in sym_rows:
            qty = int(r.get("qty") or 0)
            price = float(r.get("price") or 0)
            side = str(r.get("side") or "").upper()
            r["amount_usd"] = round(price * qty, 2)
            r["t_change"] = _format_t_change(r.get("t_before"), r.get("t_after"))
            r["date"] = _to_kst_date(r.get("datetime") or "")

            if side == "SELL" and running_qty > 0:
                sell_qty = min(qty, running_qty)
                r["pnl_usd"] = round((price - running_avg) * sell_qty, 2)
                running_qty = max(0, running_qty - qty)
                if running_qty == 0:
                    running_avg = 0.0
            elif side == "BUY":
                r["pnl_usd"] = None
                total_cost = running_avg * running_qty + price * qty
                running_qty += qty
                running_avg = total_cost / running_qty if running_qty else 0.0
            else:
                r["pnl_usd"] = None

    rows.sort(key=lambda r: (r.get("datetime") or "", r.get("symbol") or ""))
    for i, r in enumerate(rows, 1):
        r["seq"] = i


def collect_sheet_trades(app: "App") -> list[dict]:
    """토스 체결 + T메타 — Sheets 매매내역 (연번·날짜·T·가격·수량·총액·손익)."""
    from strategy.fill_reconciler import FillReconciler

    rows: list[dict] = []
    for symbol in SYMBOLS:
        st = app.state.load(symbol)
        fill_log = list(st.get("fill_log") or [])
        sym = app.cycles.get_symbol_data(symbol)
        qty = int(st.get("qty") or 0)
        cur = sym.get("current")

        current_trades: list[dict] = []
        if not is_dry(app) and app.settings.has_toss:
            try:
                order_ids = FillReconciler.collect_known_order_ids(app, symbol, st=st)
                broker_fills = app.broker.list_broker_fills(
                    symbol, days=365, max_orders=500, extra_order_ids=order_ids,
                )
                if broker_fills and qty > 0:
                    current_trades = app.cycles.display_trades_from_broker(
                        symbol, broker_fills, sym, fill_log, qty,
                    )
            except Exception:
                logger.exception("sheet broker trades %s", symbol)
        if not current_trades:
            current_trades = app.cycles._collect_trades(sym, symbol, fill_log)

        cycle_no = (cur or {}).get("cycle_no", "")
        for tr in current_trades:
            rows.append(_trade_row(
                symbol, tr,
                cycle_no=cycle_no,
                cycle_status="진행중" if cur else "",
            ))

        for c in sym.get("completed") or []:
            c_trades = list(c.get("trades") or [])
            if c_trades:
                app.cycles._recompute_t_metadata(c_trades)
            for tr in c_trades:
                rows.append(_trade_row(
                    symbol, tr,
                    cycle_no=c.get("cycle_no"),
                    cycle_status="완료",
                ))

    _enrich_sheet_trade_rows(rows)
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
